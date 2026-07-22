"""
Example showing live trading with news and prediction market integration

Demonstrates fetching news and Polymarket data for trade decisions.
"""
import asyncio
from datetime import datetime, timedelta
import logging

from fluxV.data.news import NewsManager, PolymarketSource

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    """Example of news and prediction market data integration."""

    # 1. Fetch news events for a currency
    news_manager = NewsManager()

    async with news_manager:
        # Get news for USD
        logger.info("Fetching news for USD...")
        events = await news_manager.get_news(
            currency="USD",
            from_date=datetime.now() - timedelta(days=7),
            to_date=datetime.now(),
        )
        logger.info(f"Found {len(events)} news events")

        # Get trading recommendation
        rec = news_manager.get_trading_recommendation("EURUSD", events)
        logger.info(f"Recommendation: {rec}")

        # 2. Fetch Polymarket prediction data
        source = PolymarketSource()
        try:
            markets = await source.get_economic_markets()
            logger.info(f"Found {len(markets)} prediction markets")

            for m in markets[:5]:
                logger.info(f"  Market: {m.title} | Odds: {m.outcome_prices}")
        finally:
            await source.close()


if __name__ == "__main__":
    asyncio.run(main())
