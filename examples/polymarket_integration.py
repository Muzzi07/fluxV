"""
Example using Polymarkets as a news/data source for trading
"""
import asyncio
import pandas as pd
from datetime import datetime, timedelta
from fluxV.data.news import (
    NewsManager,
    PolymarketSource,
    NewsEvent,
    NewsImpact,
    NewsSentiment
)


async def test_polymarket_integration():
    """Test Polymarket integration"""
    
    print("Testing Polymarket Integration")
    print("=" * 50)
    
    # Initialize news manager
    news_manager = NewsManager()
    
    async with news_manager:
        # Get Polymarket data for USD
        print("\n1. Fetching Polymarket data for USD...")
        polymarket_events = await news_manager.get_polymarket_data("USD", limit=5)
        
        for event in polymarket_events:
            print(f"\nEvent: {event.title}")
            print(f"  Category: {event.category}")
            print(f"  End Date: {event.end_date}")
            print(f"  Outcome Prices: {event.outcome_prices}")
            print(f"  Volume: ${event.volume:,.2f}")
            print(f"  Liquidity: ${event.liquidity:,.2f}")
        
        # Get market sentiment
        print("\n2. Getting market sentiment for EURUSD...")
        sentiment = await news_manager.get_market_sentiment(
            "EURUSD",
            include_prediction_markets=True
        )
        
        if sentiment:
            print(f"\n  Symbol: {sentiment.symbol}")
            print(f"  News Sentiment: {sentiment.news_sentiment:.2f}")
            print(f"  Prediction Market Sentiment: {sentiment.prediction_market_sentiment:.2f}")
            print(f"  Overall Sentiment: {sentiment.overall_sentiment:.2f}")
            print(f"  Confidence: {sentiment.confidence:.2f}")
            print(f"  Details: {sentiment.details}")
        
        # Get trading recommendation
        print("\n3. Getting trading recommendation...")
        events = await news_manager.get_news(
            "USD",
            from_date=datetime.now() - timedelta(days=7),
            to_date=datetime.now()
        )
        
        recommendation = news_manager.get_trading_recommendation("EURUSD", events)
        print(f"\n  Action: {recommendation['action']}")
        print(f"  Confidence: {recommendation['confidence']:.2f}")
        print(f"  Sentiment Score: {recommendation['sentiment_score']:.2f}")
        print(f"  Reasoning: {recommendation['reasoning'][:3]}...")
        print(f"  Event Count: {recommendation['event_count']}")
    
    print("\n" + "=" * 50)


async def test_polymarket_source():
    """Test PolymarketSource directly"""
    
    print("\nTesting Polymarket Source Directly")
    print("=" * 50)
    
    source = PolymarketSource()
    
    try:
        # Get economic markets
        print("\n1. Fetching economic markets...")
        economic_markets = await source.get_economic_markets()
        
        print(f"Found {len(economic_markets)} economic markets")
        for market in economic_markets[:5]:
            print(f"  - {market.title}")
            print(f"    Category: {market.category}")
            print(f"    Outcomes: {market.outcome_prices}")
        
        # Get rates markets
        print("\n2. Fetching rates markets...")
        rates_markets = await source.get_rates_markets()
        
        print(f"Found {len(rates_markets)} rates markets")
        for market in rates_markets[:5]:
            print(f"  - {market.title}")
            print(f"    End Date: {market.end_date}")
            print(f"    Volume: ${market.volume:,.2f}")
        
    finally:
        await source.close()
    
    print("\n" + "=" * 50)


async def live_trading_with_polymarket():
    """
    Example of using Polymarket sentiment for live trading decisions
    """
    print("\nLive Trading with Polymarket Sentiment")
    print("=" * 50)
    
    news_manager = NewsManager()
    
    async with news_manager:
        # Monitor sentiment for multiple symbols
        symbols = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]
        
        print("\nMonitoring market sentiment...")
        
        while True:
            for symbol in symbols:
                sentiment = await news_manager.get_market_sentiment(
                    symbol,
                    include_prediction_markets=True
                )
                
                if sentiment and abs(sentiment.overall_sentiment) > 0.3:
                    print(f"\n{symbol}:")
                    print(f"  Overall Sentiment: {sentiment.overall_sentiment:.2f}")
                    print(f"  Confidence: {sentiment.confidence:.2f}")
                    
                    if sentiment.overall_sentiment > 0.3:
                        print(f"  ⬆️  BULLISH signal for {symbol}")
                    else:
                        print(f"  ⬇️  BEARISH signal for {symbol}")
            
            # Wait before next check
            await asyncio.sleep(60)  # Check every minute


async def backtest_with_polymarket():
    """Backtest using Polymarket prediction data"""
    print("\nBacktest with Polymarket Data")
    print("=" * 50)
    
    # This would be integrated with the backtest engine
    print("Backtest would use historical Polymarket data")
    print("For example:")
    print("  - Interest rate prediction accuracy")
    print("  - Economic event outcome probability")
    print("  - Market sentiment correlation with price movements")
    
    # Placeholder for backtest logic
    print("\nCorrelation Analysis Example:")
    print("  Symbol: EURUSD")
    print("  Period: 2024 Q1")
    print("  Market Sentiment vs Price Change: r = 0.74")
    print("  Prediction Market Accuracy: 82%")
    print("  Trading Signal Profits with Sentiment: +15.3%")
    print("  Trading Signal Profits without Sentiment: +8.7%")


async def main():
    """Run all examples"""
    
    # Test Polymarket integration
    await test_polymarket_integration()
    
    # Test Polymarket source
    await test_polymarket_source()
    
    # Example backtest
    await backtest_with_polymarket()
    
    # Uncomment for live trading (would run continuously)
    # await live_trading_with_polymarket()


if __name__ == "__main__":
    asyncio.run(main())