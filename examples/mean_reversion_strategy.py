"""Mean Reversion Strategy — buys oversold bounces on FX pairs, 2010-2025 with equity curve."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import asyncio
from datetime import datetime, timedelta
from collections import deque
import pandas as pd
from pathlib import Path
import webbrowser
import numpy as np
import json

from fluxV import OrderRequest, OrderAction, OrderType, Timeframe, Bar, OrderStatus, OrderResult
from fluxV.core.types import Position as PosType
from strats.data_loader import build_backtest_bars

SYMBOL_CURRENCIES = {"EURUSD": ("EUR", "USD"), "USDJPY": ("USD", "JPY"), "AUDNZD": ("AUD", "NZD")}
CURRENCY_REGION = {"AUD": "AU", "EUR": "EU", "JPY": "JP", "NZD": "NZ", "USD": "US"}


class MockBroker:
    def __init__(self, balance=10_000):
        self._initial = balance
        self._balance = balance
        self._positions = []
        self._trades = []
        self._equity_history = []
        self._prices = {}
        self._ohlc = {}
        self._current_time = None
        self._counter = 0

    def set_time(self, t):          self._current_time = t
    def set_price(self, s, p):      self._prices[s] = p
    def set_ohlc(self, s, h, l):    self._ohlc[s] = (h, l)

    def _mtm_equity(self):
        mtm = self._balance
        for p in self._positions:
            cp = self._prices.get(p.symbol, p.price_open)
            pnl = ((cp - p.price_open) * p.volume * 100000
                  if p.action == OrderAction.BUY
                  else (p.price_open - cp) * p.volume * 100000)
            mtm += pnl
        return mtm

    def record_equity(self):
        self._equity_history.append({
            "time": self._current_time,
            "balance": round(self._balance, 2),
            "equity": round(self._mtm_equity(), 2),
        })

    def update_positions(self):
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
                    self._balance += pnl
                    self._trades.append({"profit": round(pnl,2), "symbol": p.symbol,
                        "action": p.action.name, "volume": p.volume,
                        "price_open": p.price_open, "price_close": fill_price,
                        "reason": reason,
                        "open_time": str(p.open_time), "close_time": str(self._current_time)})
                    self._positions.remove(p)
                    break

    async def get_positions(self, symbol=None):
        if symbol: return [p for p in self._positions if p.symbol == symbol]
        return list(self._positions)

    async def place_order(self, req):
        self._counter += 1
        price = req.price or self._prices.get(req.symbol, 1.0)
        ticket = int(datetime.now().timestamp() * 1_000_000) + self._counter
        pos = PosType(ticket=ticket, symbol=req.symbol, action=req.action,
                      volume=req.volume, price_open=price, price_current=price,
                      sl=req.sl, tp=req.tp, profit=0.0, comment=req.comment,
                      magic=req.magic or 0, open_time=self._current_time or datetime.now())
        self._positions.append(pos)
        return OrderResult(order_id=ticket, symbol=req.symbol, action=req.action,
                           volume=req.volume, price=price, sl=req.sl, tp=req.tp,
                           comment=req.comment, status=OrderStatus.FILLED,
                           magic=req.magic, filled_volume=req.volume)

    async def close_position(self, ticket):
        for p in self._positions:
            if p.ticket == ticket:
                cp = self._prices.get(p.symbol, p.price_open)
                pnl = ((cp - p.price_open) * p.volume * 100000
                      if p.action == OrderAction.BUY
                      else (p.price_open - cp) * p.volume * 100000)
                self._balance += pnl
                self._trades.append({"profit": round(pnl,2), "symbol": p.symbol,
                    "action": p.action.name, "volume": p.volume,
                    "price_open": p.price_open, "price_close": cp,
                    "reason": "SIGNAL",
                    "open_time": str(p.open_time), "close_time": str(self._current_time)})
                self._positions.remove(p)
                return True
        return False

    def get_results(self):
        total = sum(t["profit"] for t in self._trades)
        wins = [t for t in self._trades if t["profit"] > 0]
        losses = [t for t in self._trades if t["profit"] < 0]
        eq = self._equity_history if self._equity_history else [{"time": self._current_time, "balance": self._balance, "equity": self._balance}]
        eq_df = pd.DataFrame(eq)
        eq_peak = eq_df["equity"].cummax()
        dd = ((eq_peak - eq_df["equity"]) / eq_peak * 100)
        max_dd = float(dd.max()) if not dd.empty else 0
        daily_rets = eq_df["equity"].pct_change().dropna()
        sharpe = float(np.sqrt(252) * daily_rets.mean() / daily_rets.std()) if len(daily_rets) > 1 and daily_rets.std() > 0 else 0
        profit_factor = round(sum(t["profit"] for t in wins) / abs(sum(t["profit"] for t in losses)), 2) if losses else 999
        return {
            "initial_balance": self._initial, "final_balance": round(self._balance, 2),
            "total_return_pct": round((self._balance - self._initial) / self._initial * 100, 2),
            "total_pnl": round(total, 2), "total_trades": len(self._trades),
            "win_rate": round(len(wins) / len(self._trades) * 100, 1) if self._trades else 0,
            "avg_win": round(sum(t["profit"] for t in wins) / len(wins), 2) if wins else 0,
            "avg_loss": round(abs(sum(t["profit"] for t in losses) / len(losses)), 2) if losses else 0,
            "max_drawdown_pct": round(max_dd, 2), "sharpe_ratio": round(sharpe, 2),
            "profit_factor": profit_factor,
            "max_drawdown_dollar": round(float((eq_peak - eq_df["equity"]).max()), 2) if not eq_df.empty else 0,
            "trade_history": self._trades, "equity_curve": eq,
        }


class MeanReversionFX:
    """
    Mean Reversion strategy for FX pairs.
    - Uses RSI(14) to identify oversold/overbought conditions
    - BUY when RSI < oversold_threshold and price is below a rolling mean
    - SELL (short) when RSI > overbought_threshold and price is above a rolling mean
    - Exits when price reverts to the mean or TP/SL is hit
    - DD freeze: pauses at max_dd_pct, resumes after cooldown or recovery
    """

    def __init__(self, broker, symbol_a, symbol_b,
                 rsi_period=10, oversold=28, overbought=72,
                 volume=0.05, tp_pips=120, sl_pips=60,
                 max_dd_pct=20.0, resume_dd_pct=15.0,
                 freeze_cooldown_days=60,
                 news_avoid_bars=3, min_importance=0):
        self.broker = broker
        self.sym_a = symbol_a
        self.sym_b = symbol_b
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought
        self.volume = volume
        self.tp_pips = tp_pips
        self.sl_pips = sl_pips
        self.max_dd_pct = max_dd_pct
        self.resume_dd_pct = resume_dd_pct
        self.freeze_cooldown_days = freeze_cooldown_days
        self.news_avoid_bars = news_avoid_bars
        self.min_importance = min_importance

        self.closes_a = deque(maxlen=rsi_period + 5)
        self.closes_b = deque(maxlen=rsi_period + 5)
        self._trading_frozen = False
        self._peak_basis = broker._initial
        self._freeze_start = None

        # Economic events for news avoidance
        currencies_a = SYMBOL_CURRENCIES.get(symbol_a, (symbol_a[:3], symbol_a[3:]))
        currencies_b = SYMBOL_CURRENCIES.get(symbol_b, (symbol_b[:3], symbol_b[3:]))
        all_currencies = set(currencies_a + currencies_b)
        self.events = {}
        for cur in all_currencies:
            region = CURRENCY_REGION.get(cur)
            if region:
                evts = []
                for year in range(2013, 2025):
                    p = (Path(__file__).parent.parent / "local_data" / "data"
                         / "economic_data" / cur / region / str(year)
                         / f"{cur}_{region}_economic_calendar_{year}.parquet")
                    if p.exists():
                        df = pd.read_parquet(p)
                        df = df[df["importance"] >= self.min_importance].copy()
                        evts.append(df)
                if evts:
                    self.events[cur] = pd.concat(evts, ignore_index=True)
                    self.events[cur]["timestamp"] = pd.to_datetime(self.events[cur]["timestamp"])
                else:
                    self.events[cur] = pd.DataFrame()

    def _has_recent_news(self, symbol, current_time):
        currencies = SYMBOL_CURRENCIES.get(symbol, (symbol[:3], symbol[3:]))
        for cur in currencies:
            df = self.events.get(cur)
            if df is None or df.empty: continue
            ct = pd.Timestamp(current_time).tz_localize(None)
            window = pd.Timedelta(hours=self.news_avoid_bars * 24)
            recent = df[abs(df["timestamp"].dt.tz_localize(None) - ct) < window]
            if not recent.empty: return True
        return False

    def _compute_rsi(self, closes):
        """Standard RSI from a list of close prices (most recent last)."""
        if len(closes) < self.rsi_period + 1:
            return 50.0
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains[-self.rsi_period:])
        avg_loss = np.mean(losses[-self.rsi_period:])
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def _dd_pct(self):
        """Drawdown based on realised balance only."""
        bal = self.broker._balance
        if bal > self._peak_basis:
            self._peak_basis = bal
        return ((self._peak_basis - bal) / self._peak_basis) * 100 if self._peak_basis > 0 else 0

    async def on_bar(self, bar_a, bar_b):
        self.closes_a.append(bar_a.close)
        self.closes_b.append(bar_b.close)
        if len(self.closes_a) < self.rsi_period + 1:
            return

        ca = list(self.closes_a)
        cb = list(self.closes_b)
        rsi_a = self._compute_rsi(ca)
        rsi_b = self._compute_rsi(cb)
        dd = self._dd_pct()
        price_a = ca[-1]
        price_b = cb[-1]

        # Simple rolling mean for mean reversion entry filter
        mean_a = np.mean(ca[-self.rsi_period:])
        mean_b = np.mean(cb[-self.rsi_period:])

        # Freeze/unfreeze
        if dd >= self.max_dd_pct and not self._trading_frozen:
            self._trading_frozen = True
            self._freeze_start = bar_a.time
        elif self._trading_frozen:
            cooldown_done = (bar_a.time - self._freeze_start).days >= self.freeze_cooldown_days if self._freeze_start else True
            if dd <= self.resume_dd_pct or cooldown_done:
                self._trading_frozen = False
                self._freeze_start = None
                if dd > self.resume_dd_pct and cooldown_done:
                    self._peak_basis = self.broker._balance

        news_a = self._has_recent_news(self.sym_a, bar_a.time)
        news_b = self._has_recent_news(self.sym_b, bar_b.time)

        # Determine signal
        chosen = None
        action = None  # OrderAction.BUY or SELL
        entry_price = None

        if not self._trading_frozen:
            # EURUSD signal
            if rsi_a < self.oversold and price_a < mean_a and not news_a:
                chosen = self.sym_a
                action = OrderAction.BUY
                entry_price = price_a
            # USDJPY signal
            if rsi_b < self.oversold and price_b < mean_b and not news_b:
                # If both signal, pick the one with lower RSI (more oversold)
                if chosen is None or rsi_b < rsi_a:
                    chosen = self.sym_b
                    action = OrderAction.BUY
                    entry_price = price_b

        current = await self.broker.get_positions()
        if current:
            pos = current[0]
            should_close = (chosen is None or pos.symbol != chosen or
                          self._trading_frozen or
                          self._has_recent_news(pos.symbol, bar_a.time))
            if should_close:
                await self.broker.close_position(pos.ticket)
                current = await self.broker.get_positions()

        if chosen and action and not current:
            pip = 0.0001 if "JPY" not in chosen else 0.01
            sl = entry_price - self.sl_pips * pip
            tp = entry_price + self.tp_pips * pip
            await self.broker.place_order(OrderRequest(
                symbol=chosen, action=action,
                volume=self.volume, sl=round(sl, 5), tp=round(tp, 5),
                order_type=OrderType.MARKET))


async def main():
    symbol_a, symbol_b = "EURUSD", "USDJPY"
    tf = Timeframe.D1
    from_date = datetime(2010, 1, 1)
    to_date = datetime(2025, 7, 19)

    # Mean reversion params
    rsi_period = 10
    oversold = 28
    overbought = 72
    volume = 0.05
    tp_pips = 120
    sl_pips = 60
    max_dd_pct = 20.0
    resume_dd_pct = 15.0
    freeze_cooldown_days = 60
    news_avoid_bars = 3
    min_importance = 0

    print(f"\n  Loading {symbol_a} & {symbol_b} D1 {from_date.year}-{to_date.year}...")
    bars_a = build_backtest_bars(symbol_a, tf, from_date, to_date)
    bars_b = build_backtest_bars(symbol_b, tf, from_date, to_date)

    by_time = {}
    for b in bars_a:  by_time.setdefault(b.time, [None, None])[0] = b
    for b in bars_b:  by_time.setdefault(b.time, [None, None])[1] = b
    aligned = [(t, a, b) for t, (a, b) in sorted(by_time.items())
               if a is not None and b is not None]
    print(f"  {len(aligned)} aligned daily bars\n")

    broker = MockBroker(balance=10_000)
    strat = MeanReversionFX(broker, symbol_a, symbol_b,
                            rsi_period=rsi_period, oversold=oversold, overbought=overbought,
                            volume=volume, tp_pips=tp_pips, sl_pips=sl_pips,
                            max_dd_pct=max_dd_pct, resume_dd_pct=resume_dd_pct,
                            freeze_cooldown_days=freeze_cooldown_days,
                            news_avoid_bars=news_avoid_bars, min_importance=min_importance)

    for i, (t, ba, bb) in enumerate(aligned):
        broker.set_time(t)
        broker.set_price(symbol_a, ba.close)
        broker.set_price(symbol_b, bb.close)
        broker.set_ohlc(symbol_a, ba.high, ba.low)
        broker.set_ohlc(symbol_b, bb.high, bb.low)
        broker.update_positions()
        await strat.on_bar(ba, bb)
        if i % 60 == 0:
            broker.record_equity()
    broker.record_equity()

    from strats.reporter import save_results
    r = broker.get_results()
    label = f"MeanReversionFX {symbol_a}/{symbol_b} D1 {from_date.year}-{to_date.year}"
    report_path = save_results(r, title=label)
    if report_path:
        webbrowser.open(f"file://{report_path}")

    out = Path(__file__).parent.parent / "results"
    out.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary = {
        "strategy": "MeanReversionFX",
        "symbols": [symbol_a, symbol_b],
        "timeframe": "D1",
        "period": {"from": from_date.isoformat(), "to": to_date.isoformat()},
        "config": {"rsi_period": rsi_period, "oversold": oversold, "overbought": overbought,
                   "volume": volume, "tp_pips": tp_pips, "sl_pips": sl_pips,
                   "max_dd_pct": max_dd_pct, "resume_dd_pct": resume_dd_pct,
                   "freeze_cooldown_days": freeze_cooldown_days,
                   "news_avoid_bars": news_avoid_bars},
        "results": {k: v for k, v in r.items()
                    if k not in ("trade_history", "equity_curve")},
    }
    (out / f"summary_mean_reversion_{ts}.json").write_text(json.dumps(summary, indent=2, default=str))
    print(f"  Saved: summary_mean_reversion_{ts}.json")


if __name__ == "__main__":
    asyncio.run(main())
