"""Mean Reversion — FX with automated FixedAccountBroker. No DD logic needed in strategy."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import asyncio
from datetime import datetime
from collections import deque
import pandas as pd
from pathlib import Path
import webbrowser
import numpy as np
import json

from fluxV import OrderRequest, OrderAction, OrderType, Timeframe, OrderStatus
from strats.data_loader import build_backtest_bars

from _fixed_broker import FixedAccountBroker

SYMBOL_CURRENCIES = {"EURUSD": ("EUR", "USD"), "USDJPY": ("USD", "JPY")}
CURRENCY_REGION = {"AUD": "AU", "EUR": "EU", "JPY": "JP", "NZD": "NZ", "USD": "US"}


class MeanReversion:
    """
    Pure mean reversion strategy — no DD logic.
    FixedAccountBroker handles: profit sweeping, reserve top-up, DD freeze, cooldown.
    """

    def __init__(self, broker, symbol_a, symbol_b,
                 rsi_period=10, oversold=28, overbought=72,
                 volume=0.05, tp_pips=120, sl_pips=60,
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
        self.news_avoid_bars = news_avoid_bars
        self.min_importance = min_importance
        self.closes_a = deque(maxlen=rsi_period + 5)
        self.closes_b = deque(maxlen=rsi_period + 5)

        # Economic events
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

    async def on_bar(self, bar_a, bar_b):
        self.closes_a.append(bar_a.close)
        self.closes_b.append(bar_b.close)
        if len(self.closes_a) < self.rsi_period + 1:
            return

        ca = list(self.closes_a); cb = list(self.closes_b)
        rsi_a = self._compute_rsi(ca)
        rsi_b = self._compute_rsi(cb)
        price_a = ca[-1]; price_b = cb[-1]
        mean_a = np.mean(ca[-self.rsi_period:])
        mean_b = np.mean(cb[-self.rsi_period:])

        # Broker handles DD freeze automatically
        self.broker._auto_check_freeze(bar_a.time)

        news_a = self._has_recent_news(self.sym_a, bar_a.time)
        news_b = self._has_recent_news(self.sym_b, bar_b.time)

        # Signal
        chosen = None
        entry_price = None
        if not self.broker._trading_frozen:
            if rsi_a < self.oversold and price_a < mean_a and not news_a:
                chosen = self.sym_a
                entry_price = price_a
            if rsi_b < self.oversold and price_b < mean_b and not news_b:
                if chosen is None or rsi_b < rsi_a:
                    chosen = self.sym_b
                    entry_price = price_b

        # Manage position
        current = await self.broker.get_positions()
        if current:
            pos = current[0]
            sc = (chosen is None or pos.symbol != chosen or
                  self.broker._trading_frozen or
                  self._has_recent_news(pos.symbol, bar_a.time))
            if sc:
                await self.broker.close_position(pos.ticket)
                current = await self.broker.get_positions()

        if chosen and entry_price and not current:
            pip = 0.0001 if "JPY" not in chosen else 0.01
            sl = entry_price - self.sl_pips * pip
            tp = entry_price + self.tp_pips * pip
            result = await self.broker.place_order(OrderRequest(
                symbol=chosen, action=OrderAction.BUY,
                volume=self.volume, sl=round(sl, 5), tp=round(tp, 5),
                order_type=OrderType.MARKET))
            if result.status == OrderStatus.REJECTED:
                print(f"  [{bar_a.time.date()}] ORDER REJECTED: {result.comment}")


async def main():
    symbol_a, symbol_b = "EURUSD", "USDJPY"
    tf = Timeframe.D1
    from_date = datetime(2010, 1, 1)
    to_date = datetime(2025, 7, 19)

    rsi_period = 10
    oversold = 28
    overbought = 72
    volume = 0.05
    tp_pips = 120
    sl_pips = 60
    news_avoid_bars = 3
    min_importance = 0

    # Broker has all DD/cooldown/sweep logic built-in
    broker = FixedAccountBroker(
        base_allocation=10_000,
        reserve_start=0,
        max_dd_pct=20.0,
        resume_dd_pct=15.0,
        freeze_cooldown_days=60,
    )

    print(f"\n  Loading {symbol_a} & {symbol_b} D1 {from_date.year}-{to_date.year}...")
    bars_a = build_backtest_bars(symbol_a, tf, from_date, to_date)
    bars_b = build_backtest_bars(symbol_b, tf, from_date, to_date)

    by_time = {}
    for b in bars_a:  by_time.setdefault(b.time, [None, None])[0] = b
    for b in bars_b:  by_time.setdefault(b.time, [None, None])[1] = b
    aligned = [(t, a, b) for t, (a, b) in sorted(by_time.items())
               if a is not None and b is not None]
    print(f"  {len(aligned)} aligned daily bars\n")

    strat = MeanReversion(broker, symbol_a, symbol_b,
                          rsi_period=rsi_period, oversold=oversold, overbought=overbought,
                          volume=volume, tp_pips=tp_pips, sl_pips=sl_pips,
                          news_avoid_bars=news_avoid_bars,
                          min_importance=min_importance)

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
    label = f"Auto-Fixed MeanReversion {symbol_a}/{symbol_b} D1 {from_date.year}-{to_date.year}"
    report_path = save_results(r, title=label)
    if report_path:
        webbrowser.open(f"file://{report_path}")

    out = Path(__file__).parent.parent / "results"
    out.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary = {
        "strategy": "AutoFixed-MeanReversion",
        "symbols": [symbol_a, symbol_b],
        "timeframe": "D1",
        "period": {"from": from_date.isoformat(), "to": to_date.isoformat()},
        "config": {"rsi_period": rsi_period, "oversold": oversold, "overbought": overbought,
                   "volume": volume, "tp_pips": tp_pips, "sl_pips": sl_pips,
                   "news_avoid_bars": news_avoid_bars},
        "results": {k: v for k, v in r.items()
                    if k not in ("trade_history", "equity_curve")},
    }
    (out / f"summary_auto_fixed_mr_{ts}.json").write_text(json.dumps(summary, indent=2, default=str))
    print(f"  Saved: summary_auto_fixed_mr_{ts}.json")


if __name__ == "__main__":
    asyncio.run(main())
