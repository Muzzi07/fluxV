"""
Example showing how to incorporate news data into backtesting

Demonstrates using NewsManager for event-driven trading signals.
"""
import asyncio
from datetime import datetime, timedelta
import logging

from fluxV.backtest.engine import BacktestEngine
from fluxV.backtest.mock import MockBroker
from fluxV.core.types import Timeframe, OrderAction
from fluxV.data.news import NewsManager, NewsImpact, NewsSentiment

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def news_aware_strategy(bar):
    """Strategy callback that uses news events for trade decisions."""
    broker = bar._engine.broker  # access broker from engine
    account = await broker.get_account_info()

    # Example logic: print bar info
    logger.info(
        f"[{bar.time}] O:{bar.open:.5f} H:{bar.high:.5f} "
        f"L:{bar.low:.5f} C:{bar.close:.5f} V:{bar.volume}"
    )
    # In a real strategy, you would check news events and place orders
    # based on both technical and fundamental data.


async def main():
    """Run a backtest with news integration."""
    # Create a mock broker for backtesting
    broker = MockBroker(initial_balance=10_000, commission=0.0, spread=0.0001)

    # Create the backtest engine
    engine = BacktestEngine(broker, initial_balance=10_000)

    # Run the backtest
    report = await engine.run(
        symbol="EURUSD",
        timeframe=Timeframe.H1,
        from_date=datetime(2024, 1, 1),
        to_date=datetime(2024, 1, 31),
        strategy_callback=news_aware_strategy,
    )

    logger.info(f"Backtest complete: {report.get('total_trades', 0)} trades")


if __name__ == "__main__":
    asyncio.run(main())
