"""Basic fluxV example with results saved to a folder."""
import sys, os, webbrowser
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import asyncio
from datetime import datetime
from collections import deque
import pandas as pd
from pathlib import Path

from fluxV import OrderRequest, OrderAction, OrderType, Timeframe, Bar, OrderStatus


def load_bars(symbol, tf, from_date, to_date):
    label = {Timeframe.H1: "H1", Timeframe.H4: "H4", Timeframe.D1: "D1"}[tf]
    base = Path(__file__).parent.parent / "local_data" / "data" / "forexsb_clean" / symbol
    bars = []
    for year in range(from_date.year, to_date.year + 1):
        p = base / str(year) / f"{label}.parquet"
        if not p.exists(): continue
        df = pd.read_parquet(p).sort_values("Time")
        m = (df["Time"] >= pd.Timestamp(from_date).tz_localize("UTC")) & \
            (df["Time"] <= pd.Timestamp(to_date).tz_localize("UTC"))
        for _, r in df[m].iterrows():
            bars.append(Bar(time=r["Time"].to_pydatetime(), open=float(r["Open"]),
                           high=float(r["High"]), low=float(r["Low"]),
                           close=float(r["Close"]), volume=int(r["Volume"]),
                           tick_volume=int(r["Volume"])))
    return bars


class MockBroker:
    def __init__(self, bars, balance=10_000):
        self._bars = bars
        self._balance = balance
        self._positions = []
        self._trades = []
        self._equity = []
        self._current_price = {}
        self._current_time = None
        self._counter = 0

    def set_current_time(self, t):     self._current_time = t
    def set_current_price(self, s, p): self._current_price[s] = p

    def record_equity(self):
        self._equity.append({"time": self._current_time, "balance": self._balance})

    def update_positions(self, price):
        for p in self._positions:
            p.price_current = price
            p.profit = ((price - p.price_open) * p.volume * 100000 
                       if p.action == OrderAction.BUY 
                       else (p.price_open - price) * p.volume * 100000)

    async def get_positions(self, symbol=None):
        return [p for p in self._positions if symbol is None or p.symbol == symbol]

    async def place_order(self, req):
        from fluxV import OrderResult
        from fluxV.core.types import Position as PosType
        self._counter += 1
        price = req.price or self._current_price.get(req.symbol, 1.0)
        ticket = int(asyncio.get_running_loop().time() * 1_000_000) + self._counter
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
                cp = self._current_price.get(p.symbol, p.price_open)
                pnl = ((cp - p.price_open) * p.volume * 100000 
                      if p.action == OrderAction.BUY 
                      else (p.price_open - cp) * p.volume * 100000)
                self._balance += pnl
                self._trades.append({
                    "time": self._current_time,
                    "symbol": p.symbol,
                    "action": p.action.name,
                    "volume": p.volume,
                    "entry": p.price_open,
                    "exit": cp,
                    "profit": pnl,
                })
                self._positions.remove(p)
                return True
        return False

    def get_results(self):
        total_pnl = sum(t["profit"] for t in self._trades)
        win_trades = [t for t in self._trades if t["profit"] > 0]
        loss_trades = [t for t in self._trades if t["profit"] < 0]
        return {
            "initial_balance": 10000,
            "final_balance": self._balance,
            "total_return_pct": ((self._balance - 10000) / 10000) * 100,
            "total_pnl": total_pnl,
            "total_trades": len(self._trades),
            "winning_trades": len(win_trades),
            "losing_trades": len(loss_trades),
            "win_rate": len(win_trades) / len(self._trades) * 100 if self._trades else 0,
            "avg_profit": total_pnl / len(self._trades) if self._trades else 0,
            "avg_win": sum(t["profit"] for t in win_trades) / len(win_trades) if win_trades else 0,
            "avg_loss": sum(t["profit"] for t in loss_trades) / len(loss_trades) if loss_trades else 0,
            "trade_history": self._trades,
            "equity_curve": self._equity,
        }


class SMACrossover:
    def __init__(self, broker, symbol, fast=10, slow=30, volume=0.1):
        self.broker = broker
        self.symbol = symbol
        self.fast = fast
        self.slow = slow
        self.volume = volume
        self.closes = deque(maxlen=slow + 5)
        self.in_position = False

    async def on_bar(self, bar):
        self.closes.append(bar.close)
        if len(self.closes) < self.slow:
            return
        vals = list(self.closes)
        fast_sma = sum(vals[-self.fast:]) / self.fast
        slow_sma = sum(vals[-self.slow:]) / self.slow

        if self.in_position and fast_sma < slow_sma:
            for p in await self.broker.get_positions(self.symbol):
                await self.broker.close_position(p.ticket)
            self.in_position = False
        elif not self.in_position and fast_sma > slow_sma:
            r = await self.broker.place_order(OrderRequest(
                symbol=self.symbol, action=OrderAction.BUY,
                volume=self.volume, order_type=OrderType.MARKET))
            if r:
                self.in_position = True


async def main():
    symbol, tf = "EURUSD", Timeframe.H1
    from_date, to_date = datetime(2024, 1, 1), datetime(2025, 1, 1)

    bars = load_bars(symbol, tf, from_date, to_date)
    print(f"{symbol} H1 2024  ({len(bars)} bars)\n")

    broker = MockBroker(bars)
    strat = SMACrossover(broker, symbol, fast=10, slow=30, volume=0.1)

    for i, bar in enumerate(bars):
        broker.set_current_time(bar.time)
        broker.set_current_price(symbol, bar.close)
        broker.update_positions(bar.close)
        await strat.on_bar(bar)
        if i % 100 == 0:
            broker.record_equity()
    broker.record_equity()

    r = broker.get_results()

    # ── Save results ───────────────────────────────────────────
    from strats.reporter import save_results
    report_path = save_results(r, title=f"SMA Crossover {symbol} H1 2024")
    if report_path:
        print(f"  Opening browser at file://{report_path}...")
        opened = webbrowser.open(f"file://{report_path}")
        if not opened:
            import subprocess
            subprocess.run(["open", report_path])


if __name__ == "__main__":
    asyncio.run(main())
