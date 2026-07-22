"""
Backtest simulation example using the BacktestEngine

This demonstrates running a full backtest with the engine,
loading data, processing bars, and evaluating performance.
"""
import asyncio
import logging
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

from fluxV import (
    create_broker,
    setup_logging,
    OrderRequest,
    OrderAction,
    OrderType,
    Timeframe,
)
from fluxV.backtest.engine import BacktestEngine
from fluxV.backtest.data import DataLoader
from fluxV.backtest.performance import PerformanceAnalyzer

# Setup logging
setup_logging(level="INFO")
logger = logging.getLogger(__name__)


async def moving_average_strategy(bar, broker, symbol="EURUSD", fast=10, slow=30, volume=0.1):
    """
    Simple moving average crossover strategy callback for BacktestEngine.

    Args:
        bar: Current Bar being processed
        broker: MockBroker instance
        symbol: Trading symbol
        fast: Fast MA period
        slow: Slow MA period
        volume: Trade volume

    Returns:
        OrderRequest if a trade should be placed, else None
    """
    # Get recent bars for MA calculation
    bars = await broker.get_rates_latest(symbol, Timeframe.H1, slow + 1)

    if len(bars) < slow:
        return None

    closes = [b.close for b in bars]
    fast_ma = sum(closes[-fast:]) / fast
    slow_ma = sum(closes[-slow:]) / slow

    # Get current positions
    positions = await broker.get_positions(symbol)

    # Trading logic
    if fast_ma > slow_ma and not positions:
        # Buy signal
        order = OrderRequest(
            symbol=symbol,
            action=OrderAction.BUY,
            volume=volume,
            order_type=OrderType.MARKET,
            sl=bar.close * 0.99,
            tp=bar.close * 1.01,
            comment="MA Crossover Long"
        )
        result = await broker.place_order(order)
        logger.info(f"BUY at {bar.time}: {bar.close:.5f} (Order #{result.order_id})")

    elif fast_ma < slow_ma and positions:
        # Sell signal - close positions
        for pos in positions:
            if pos.symbol == symbol:
                success = await broker.close_position(pos.ticket)
                if success:
                    logger.info(
                        f"SELL (CLOSE) at {bar.time}: {bar.close:.5f} "
                        f"- Profit: ${pos.profit:.2f}"
                    )

    return None


async def run_backtest():
    """Run a complete backtest simulation."""
    print("=" * 60)
    print("  fluxV Backtest Simulation")
    print("=" * 60)

    # 1. Create the mock broker
    logger.info("Creating mock broker...")
    broker = await create_broker(
        "backtest",
        initial_balance=10000,
        commission=0.0,
        slippage=0.0001,
        spread=0.0002,
    )

    await broker.connect()

    # 2. Generate or load sample data
    logger.info("Generating sample EURUSD data...")
    end_date = datetime(2024, 12, 31)
    start_date = datetime(2024, 1, 1)

    sample_data = DataLoader.generate_sample_data(
        symbol="EURUSD",
        start_date=start_date,
        end_date=end_date,
        timeframe=Timeframe.H1,
        base_price=1.1000,
        trend=0.05,
        volatility=0.002,
    )

    # 3. Load data into the broker
    broker.load_data("EURUSD", Timeframe.H1, sample_data)
    logger.info(f"Loaded {len(sample_data)} bars of data")

    # 4. Create and run the backtest engine
    engine = BacktestEngine(broker, initial_balance=10000)

    async def strategy_callback(bar):
        await moving_average_strategy(bar, broker)

    logger.info("Starting backtest...")
    results = await engine.run(
        symbol="EURUSD",
        timeframe=Timeframe.H1,
        from_date=start_date,
        to_date=end_date,
        strategy_callback=strategy_callback,
    )

    # 5. Display results
    print("\n" + "=" * 60)
    print("  Backtest Results")
    print("=" * 60)
    print(f"  Initial Balance:  ${results.get('initial_balance', 0):>10.2f}")
    print(f"  Final Balance:    ${results.get('final_balance', 0):>10.2f}")
    print(f"  Total Profit:     ${results.get('total_profit', 0):>10.2f}")
    print(f"  Total Trades:      {results.get('total_trades', 0):>10}")
    print(f"  Win Rate:           {results.get('win_rate', 0):>9.1f}%")
    print(f"  Max Drawdown:      {results.get('max_drawdown', 0):>9.2f}%")
    print(f"  Profit Factor:      {results.get('profit_factor', 0):>9.2f}")
    print(f"  Sharpe Ratio:       {results.get('sharpe_ratio', 0):>9.4f}")
    print(f"  Sortino Ratio:      {results.get('sortino_ratio', 0):>9.4f}")
    print(f"  Calmar Ratio:       {results.get('calmar_ratio', 0):>9.4f}")
    print(f"  Avg Trade:         ${results.get('avg_trade', 0):>10.2f}")
    print(f"  Avg Win:           ${results.get('avg_win', 0):>10.2f}")
    print(f"  Avg Loss:          ${results.get('avg_loss', 0):>10.2f}")
    print(f"  Bars Processed:     {results.get('total_bars', 0):>10}")

    # 6. Show equity curve summary
    equity_curve = results.get('equity_curve', [])
    if len(equity_curve) > 0:
        equities = [e['equity'] for e in equity_curve]
        print(f"\n  Equity Curve:")
        print(f"    Start: ${equities[0]:.2f}")
        print(f"    End:   ${equities[-1]:.2f}")
        print(f"    Low:   ${min(equities):.2f}")
        print(f"    High:  ${max(equities):.2f}")

    # 7. Show trade history summary
    trade_history = results.get('trade_history', [])
    if len(trade_history) > 0:
        winning = [t for t in trade_history if t['profit'] > 0]
        losing = [t for t in trade_history if t['profit'] < 0]
        print(f"\n  Trade History:")
        print(f"    Winning Trades: {len(winning)}")
        print(f"    Losing Trades:  {len(losing)}")
        if winning:
            print(f"    Best Trade:     ${max(t['profit'] for t in winning):.2f}")
        if losing:
            print(f"    Worst Trade:    ${min(t['profit'] for t in losing):.2f}")

    print("\n" + "=" * 60)
    print("  Backtest Complete!")
    print("=" * 60)

    await broker.disconnect()


async def main():
    """Run the backtest simulation."""
    try:
        await run_backtest()
    except KeyboardInterrupt:
        print("\nBacktest interrupted by user.")
    except Exception as e:
        logger.exception(f"Backtest failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
