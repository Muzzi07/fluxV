"""Automated Fixed Account Broker.

Core rules:
- base_allocation: each trade targets this size (e.g. $10,000)
- Winners: profit → reserve, trading_balance instantly restored to base_allocation
- Losers: trading_balance drops, reserve auto-tops-up if possible
- Drawdown freeze: if total_equity DD >= max_dd_pct, auto-freeze + cooldown
- Auto-resume after cooldown or recovery
"""

import asyncio
from datetime import datetime
import pandas as pd
import numpy as np

from fluxV import OrderRequest, OrderAction, OrderType, OrderStatus, OrderResult
from fluxV.core.types import Position as PosType


class FixedAccountBroker:
    def __init__(self, base_allocation=10_000, reserve_start=0,
                 max_dd_pct=20.0, resume_dd_pct=15.0,
                 freeze_cooldown_days=60):
        # Account state
        self.base_allocation = base_allocation
        self.trading_balance = base_allocation
        self.reserve = reserve_start

        # DD freeze params
        self.max_dd_pct = max_dd_pct
        self.resume_dd_pct = resume_dd_pct
        self.freeze_cooldown_days = freeze_cooldown_days
        self._trading_frozen = False
        self._peak_equity = base_allocation + reserve_start
        self._freeze_start = None

        # Position tracking
        self._positions = []
        self._trades = []
        self._equity_history = []
        self._prices = {}
        self._ohlc = {}
        self._current_time = None
        self._counter = 0

        self._initial_total = base_allocation + reserve_start

    # ── Properties ──────────────────────────────────────────────

    @property
    def total_equity(self):
        """Full account value: trading_balance + reserve + unrealised PnL."""
        mtm = self.trading_balance + self.reserve
        for p in self._positions:
            cp = self._prices.get(p.symbol, p.price_open)
            pnl = ((cp - p.price_open) * p.volume * 100000
                  if p.action == OrderAction.BUY
                  else (p.price_open - cp) * p.volume * 100000)
            mtm += pnl
        return mtm

    @property
    def drawdown_pct(self):
        """Current DD % from peak total_equity."""
        eq = self.total_equity
        if eq > self._peak_equity:
            self._peak_equity = eq
        return ((self._peak_equity - eq) / self._peak_equity) * 100 if self._peak_equity > 0 else 0

    @property
    def available_for_trade(self):
        """How much is available for the next trade.
        - If balance >= base_allocation: trade at full base_allocation
        - If balance < base_allocation but >= 30% of base: trade at reduced size (what's available)
        - If balance < 30% of base: only trade with explicit override (override=True)
        """
        min_threshold = self.base_allocation * 0.3
        if self.trading_balance >= self.base_allocation:
            return self.base_allocation
        elif self.trading_balance >= min_threshold:
            return min(self.trading_balance, self.base_allocation)
        return 0.0  # Below 30% — blocked unless override

    # ── Lifecycle ───────────────────────────────────────────────

    def set_time(self, t):
        self._current_time = t

    def set_price(self, symbol, price):
        self._prices[symbol] = price

    def set_ohlc(self, symbol, high, low):
        self._ohlc[symbol] = (high, low)

    def record_equity(self):
        self._equity_history.append({
            "time": self._current_time,
            "trading_balance": round(self.trading_balance, 2),
            "reserve": round(self.reserve, 2),
            "equity": round(self.total_equity, 2),
        })

    # ── Core automation: profit sweeping + DD freeze ────────────

    def _auto_sweep(self, pnl):
        """
        Called automatically after every position close.
        Winners: profit → reserve, trading_balance → base_allocation.
        Losers: trading_balance drops, reserve auto tops up.
        """
        if pnl > 0:
            # Profit goes to reserve, trading balance resets to base
            self.reserve += pnl
            self.trading_balance = self.base_allocation
        else:
            # Loss reduces trading balance
            loss = abs(pnl)
            self.trading_balance -= loss
            # Auto top-up from reserve back to base_allocation
            if self.trading_balance < self.base_allocation:
                shortfall = self.base_allocation - self.trading_balance
                topup = min(shortfall, self.reserve)
                self.reserve -= topup
                self.trading_balance += topup

    def _auto_check_freeze(self, current_time):
        """Check DD and auto-freeze/unfreeze."""
        dd = self.drawdown_pct

        if dd >= self.max_dd_pct and not self._trading_frozen:
            self._trading_frozen = True
            self._freeze_start = current_time
        elif self._trading_frozen:
            cooldown_done = (current_time - self._freeze_start).days >= self.freeze_cooldown_days if self._freeze_start else True
            if dd <= self.resume_dd_pct or cooldown_done:
                self._trading_frozen = False
                self._freeze_start = None
                if dd > self.resume_dd_pct and cooldown_done:
                    # Reset peak to current equity so we can trade again
                    self._peak_equity = self.total_equity

    # ── Position management ─────────────────────────────────────

    def update_positions(self):
        """Check TP/SL against bar OHLC and auto-close + sweep."""
        to_close = []
        for p in self._positions:
            cp = self._prices.get(p.symbol, p.price_open)
            high, low = self._ohlc.get(p.symbol, (cp, cp))
            p.price_current = cp
            p.profit = ((cp - p.price_open) * p.volume * 100000
                       if p.action == OrderAction.BUY
                       else (p.price_open - cp) * p.volume * 100000)
            if p.tp and high >= p.tp:
                to_close.append((p.ticket, p.tp, "TP"))
            elif p.sl and low <= p.sl:
                to_close.append((p.ticket, p.sl, "SL"))
        for ticket, fill_price, reason in to_close:
            for p in self._positions:
                if p.ticket == ticket:
                    pnl = ((fill_price - p.price_open) * p.volume * 100000
                          if p.action == OrderAction.BUY
                          else (p.price_open - fill_price) * p.volume * 100000)
                    self._auto_sweep(pnl)
                    self._trades.append({
                        "profit": round(pnl, 2), "symbol": p.symbol,
                        "action": p.action.name, "volume": p.volume,
                        "price_open": p.price_open, "price_close": fill_price,
                        "reason": reason,
                        "open_time": str(p.open_time),
                        "close_time": str(self._current_time),
                    })
                    self._positions.remove(p)
                    break

    async def get_positions(self, symbol=None):
        if symbol:
            return [p for p in self._positions if p.symbol == symbol]
        return list(self._positions)

    async def place_order(self, req, override=False):
        """Place an order. If balance < base_allocation, rejects unless override=True.
        Override allows trading below the 30% threshold (recovery mode)."""
        self._counter += 1
        price = req.price or self._prices.get(req.symbol, 1.0)
        ticket = int(datetime.now().timestamp() * 1_000_000) + self._counter

        # Check if we can trade
        avail = self.available_for_trade
        min_threshold = self.base_allocation * 0.3

        if avail <= 0:
            if self.trading_balance < min_threshold and not override:
                return OrderResult(order_id=-1, symbol=req.symbol, action=req.action,
                                   volume=0, price=0, sl=0, tp=0,
                                   comment=f"BLOCKED: balance ${self.trading_balance:.0f} below 30% threshold (${min_threshold:.0f}), use override=True to trade",
                                   status=OrderStatus.REJECTED,
                                   magic=req.magic, filled_volume=0)

        # Calculate volume with leverage check
        pip = 0.0001 if "JPY" not in req.symbol else 0.01
        actual_avail = self.trading_balance if override else avail
        if actual_avail <= 0:
            return OrderResult(order_id=-1, symbol=req.symbol, action=req.action,
                               volume=0, price=0, sl=0, tp=0,
                               comment="REJECTED: insufficient funds",
                               status=OrderStatus.REJECTED,
                               magic=req.magic, filled_volume=0)

        notional_per_lot = 100000
        margin_per_lot = notional_per_lot / 30
        max_lots = actual_avail / margin_per_lot if margin_per_lot > 0 else 0
        vol = min(req.volume, round(max_lots, 2))
        vol = max(0.01, vol)

        pos = PosType(ticket=ticket, symbol=req.symbol, action=req.action,
                      volume=vol, price_open=price, price_current=price,
                      sl=req.sl, tp=req.tp, profit=0.0, comment=req.comment,
                      magic=req.magic or 0,
                      open_time=self._current_time or datetime.now())
        self._positions.append(pos)
        return OrderResult(order_id=ticket, symbol=req.symbol, action=req.action,
                           volume=vol, price=price, sl=req.sl, tp=req.tp,
                           comment=req.comment, status=OrderStatus.FILLED,
                           magic=req.magic, filled_volume=vol)

    async def close_position(self, ticket):
        for p in self._positions:
            if p.ticket == ticket:
                cp = self._prices.get(p.symbol, p.price_open)
                pnl = ((cp - p.price_open) * p.volume * 100000
                      if p.action == OrderAction.BUY
                      else (p.price_open - cp) * p.volume * 100000)
                self._auto_sweep(pnl)
                self._trades.append({
                    "profit": round(pnl, 2), "symbol": p.symbol,
                    "action": p.action.name, "volume": p.volume,
                    "price_open": p.price_open, "price_close": cp,
                    "reason": "SIGNAL",
                    "open_time": str(p.open_time),
                    "close_time": str(self._current_time),
                })
                self._positions.remove(p)
                return True
        return False

    # ── Results ─────────────────────────────────────────────────

    def get_results(self):
        total = sum(t["profit"] for t in self._trades)
        wins = [t for t in self._trades if t["profit"] > 0]
        losses = [t for t in self._trades if t["profit"] < 0]

        eq = self._equity_history if self._equity_history else [{
            "time": self._current_time,
            "trading_balance": self.trading_balance,
            "reserve": self.reserve,
            "equity": self.total_equity,
        }]
        eq_df = pd.DataFrame(eq)
        # Map trading_balance → balance for reporter compatibility
        if "trading_balance" in eq_df.columns:
            eq_df["balance"] = eq_df["trading_balance"]

        eq_peak = eq_df["equity"].cummax()
        dd = ((eq_peak - eq_df["equity"]) / eq_peak * 100)
        max_dd = float(dd.max()) if not dd.empty else 0

        daily_rets = eq_df["equity"].pct_change().dropna()
        sharpe = float(np.sqrt(252) * daily_rets.mean() / daily_rets.std()) if len(daily_rets) > 1 and daily_rets.std() > 0 else 0

        pf = round(sum(t["profit"] for t in wins) / abs(sum(t["profit"] for t in losses)), 2) if losses else 999

        return {
            "initial_balance": self._initial_total,
            "trading_balance": round(self.trading_balance, 2),
            "reserve": round(self.reserve, 2),
            "final_balance": round(self.total_equity, 2),
            "total_return_pct": round((self.total_equity - self._initial_total) / self._initial_total * 100, 2),
            "total_pnl": round(total, 2),
            "total_trades": len(self._trades),
            "win_rate": round(len(wins) / len(self._trades) * 100, 1) if self._trades else 0,
            "avg_win": round(sum(t["profit"] for t in wins) / len(wins), 2) if wins else 0,
            "avg_loss": round(abs(sum(t["profit"] for t in losses) / len(losses)), 2) if losses else 0,
            "max_drawdown_pct": round(max_dd, 2),
            "sharpe_ratio": round(sharpe, 2),
            "profit_factor": pf,
            "max_drawdown_dollar": round(float((eq_peak - eq_df["equity"]).max()), 2) if not eq_df.empty else 0,
            "trade_history": self._trades,
            "equity_curve": eq,
        }
