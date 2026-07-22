"""Dual Momentum — FX with automated FixedAccountBroker. No DD logic needed in strategy."""
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


class DualMomentum:
    """
    Pure momentum strategy — no DD logic.
    FixedAccountBroker handles: profit sweeping, reserve top-up, DD freeze, cooldown.
    Strategy just: read momentum, signal entry/exit, place orders.
    """

    def __init__(self, broker, symbol_a, symbol_b,
                 lookback=20, volume=0.1,
                 tp_pips=200, sl_pips=80,
                 news_avoid_bars=6, min_importance=0):
        self.broker = broker
        self.sym_a = symbol_a
        self.sym_b = symbol_b
        self.lookback = lookback
        self.volume = volume
        self.tp_pips = tp_pips
        self.sl_pips = sl_pips
        self.news_avoid_bars = news_avoid_bars
        self.min_importance = min_importance
        self.closes_a = deque(maxlen=lookback + 5)
        self.closes_b = deque(maxlen=lookback + 5)

        # Load economic events
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

    async def on_bar(self, bar_a, bar_b):
        self.closes_a.append(bar_a.close)
        self.closes_b.append(bar_b.close)
        if len(self.closes_a) < self.lookback:
            return

        ca = list(self.closes_a); cb = list(self.closes_b)
        ret_a = (ca[-1] / ca[-self.lookback]) - 1
        ret_b = (cb[-1] / cb[-self.lookback]) - 1

        # Broker handles DD freeze automatically
        self.broker._auto_check_freeze(bar_a.time)

        news_a = self._has_recent_news(self.sym_a, bar_a.time)
        news_b = self._has_recent_news(self.sym_b, bar_b.time)

        # — Recovery mode —
        # If trading_balance is below 30% of base_allocation, the broker's
        # available_for_trade returns 0 and blocks regular trades.
        # We detect this and use override=True with scaled-down volume to climb out.
        min_threshold = self.broker.base_allocation * 0.3
        in_recovery = self.broker.trading_balance < min_threshold

        # Signal
        if self.broker._trading_frozen:
            chosen = None
        elif ret_a > ret_b and ret_a > 0 and not news_a:
            chosen, price = self.sym_a, ca[-1]
        elif ret_b > ret_a and ret_b > 0 and not news_b:
            chosen, price = self.sym_b, cb[-1]
        else:
            chosen = None

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

        if chosen and not current:
            pip = 0.0001 if "JPY" not in chosen else 0.01
            sl = price - self.sl_pips * pip
            tp = price + self.tp_pips * pip

            if in_recovery:
                # Scale volume to what balance can safely support, use override
                frac = self.broker.trading_balance / self.broker.base_allocation
                vol = round(self.volume * max(frac, 0.05), 2)  # min 5% of normal
                vol = max(0.01, vol)
                result = await self.broker.place_order(
                    OrderRequest(
                        symbol=chosen, action=OrderAction.BUY,
                        volume=vol, sl=round(sl, 5), tp=round(tp, 5),
                        order_type=OrderType.MARKET,
                        comment=f"RECOVERY {frac:.0%}"),
                    override=True)
            else:
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

    lookback = 20
    volume = 0.1
    tp_pips = 200
    sl_pips = 80
    news_avoid_bars = 6
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

    strat = DualMomentum(broker, symbol_a, symbol_b,
                         lookback=lookback, volume=volume,
                         tp_pips=tp_pips, sl_pips=sl_pips,
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
    label = f"Auto-Fixed DualMomentum {symbol_a}/{symbol_b} D1 {from_date.year}-{to_date.year}"
    report_path = save_results(r, title=label)
    if report_path:
        webbrowser.open(f"file://{report_path}")

    out = Path(__file__).parent.parent / "results"
    out.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary = {
        "strategy": "AutoFixed-DualMomentum",
        "symbols": [symbol_a, symbol_b],
        "timeframe": "D1",
        "period": {"from": from_date.isoformat(), "to": to_date.isoformat()},
        "config": {"lookback": lookback, "volume": volume,
                   "tp_pips": tp_pips, "sl_pips": sl_pips,
                   "news_avoid_bars": news_avoid_bars},
        "results": {k: v for k, v in r.items()
                    if k not in ("trade_history", "equity_curve")},
    }
    (out / f"summary_auto_fixed_mom_{ts}.json").write_text(json.dumps(summary, indent=2, default=str))
    print(f"  Saved: summary_auto_fixed_mom_{ts}.json")


if __name__ == "__main__":
    asyncio.run(main())
