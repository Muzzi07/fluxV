import asyncio
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Union
from dataclasses import dataclass, field
from enum import Enum
import json
import logging
import aiohttp
from pathlib import Path

logger = logging.getLogger(__name__)


class NewsImpact(Enum):
    """News impact level"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class NewsSentiment(Enum):
    """News sentiment"""
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class NewsSource(Enum):
    """News sources"""
    FOREX_FACTORY = "forexfactory"
    DAILYFX = "dailyfx"
    INVESTING = "investing"
    POLYMARKET = "polymarket"
    REUTERS = "reuters"
    BLOOMBERG = "bloomberg"
    YAHOO = "yahoo"
    CUSTOM = "custom"


@dataclass
class NewsEvent:
    """News event data"""
    title: str
    time: datetime
    currency: str
    impact: NewsImpact
    actual: Optional[float] = None
    forecast: Optional[float] = None
    previous: Optional[float] = None
    sentiment: NewsSentiment = NewsSentiment.NEUTRAL
    description: Optional[str] = None
    source: NewsSource = NewsSource.CUSTOM
    url: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    confidence: float = 1.0  # Confidence in the data (0-1)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'title': self.title,
            'time': self.time.isoformat(),
            'currency': self.currency,
            'impact': self.impact.value,
            'actual': self.actual,
            'forecast': self.forecast,
            'previous': self.previous,
            'sentiment': self.sentiment.value,
            'description': self.description,
            'source': self.source.value,
            'url': self.url,
            'tags': self.tags,
            'confidence': self.confidence
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'NewsEvent':
        """Create from dictionary"""
        return cls(
            title=data['title'],
            time=datetime.fromisoformat(data['time']),
            currency=data['currency'],
            impact=NewsImpact(data['impact']),
            actual=data.get('actual'),
            forecast=data.get('forecast'),
            previous=data.get('previous'),
            sentiment=NewsSentiment(data.get('sentiment', 'neutral')),
            description=data.get('description'),
            source=NewsSource(data.get('source', 'custom')),
            url=data.get('url'),
            tags=data.get('tags', []),
            confidence=data.get('confidence', 1.0)
        )


@dataclass
class PolymarketEvent:
    """Polymarket prediction market data"""
    event_id: str
    title: str
    description: str
    category: str
    end_date: datetime
    outcome_prices: Dict[str, float]  # Outcome -> Probability
    volume: float
    liquidity: float
    open_interest: float
    last_updated: datetime
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'event_id': self.event_id,
            'title': self.title,
            'description': self.description,
            'category': self.category,
            'end_date': self.end_date.isoformat(),
            'outcome_prices': self.outcome_prices,
            'volume': self.volume,
            'liquidity': self.liquidity,
            'open_interest': self.open_interest,
            'last_updated': self.last_updated.isoformat()
        }


@dataclass
class MarketSentiment:
    """Aggregated market sentiment from multiple sources"""
    symbol: str
    timestamp: datetime
    news_sentiment: float  # -1 to 1
    social_sentiment: float  # -1 to 1
    prediction_market_sentiment: float  # -1 to 1
    overall_sentiment: float  # -1 to 1
    confidence: float  # 0-1
    source_weights: Dict[str, float]
    details: Dict[str, Any]


class NewsManager:
    """Manage news data from multiple sources"""
    
    def __init__(
        self,
        cache_dir: Optional[str] = None,
        cache_ttl: int = 3600  # 1 hour cache TTL
    ):
        self.cache_dir = Path(cache_dir) if cache_dir else Path("./news_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, Dict] = {}
        self._session: Optional[aiohttp.ClientSession] = None
        
    async def __aenter__(self):
        self._session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()
    
    async def get_news(
        self,
        currency: str,
        from_date: datetime,
        to_date: datetime,
        sources: Optional[List[NewsSource]] = None,
        impact_min: Optional[NewsImpact] = None,
        force_refresh: bool = False
    ) -> List[NewsEvent]:
        """
        Get news events for a currency
        
        Args:
            currency: Currency code (e.g., 'USD', 'EUR')
            from_date: Start date
            to_date: End date
            sources: List of sources to query
            impact_min: Minimum impact level
            force_refresh: Force refresh cache
            
        Returns:
            List of NewsEvent objects
        """
        # Check cache first
        cache_key = f"{currency}_{from_date.date()}_{to_date.date()}_{sources}"
        
        if not force_refresh and cache_key in self._cache:
            cached_data = self._cache[cache_key]
            if datetime.now() - cached_data['timestamp'] < timedelta(seconds=self.cache_ttl):
                events = [NewsEvent.from_dict(d) for d in cached_data['events']]
                return self._filter_events(events, impact_min)
        
        # Fetch from sources
        events = []
        sources = sources or list(NewsSource)
        
        # Create tasks for each source
        tasks = []
        for source in sources:
            if source == NewsSource.FOREX_FACTORY:
                tasks.append(self._fetch_forexfactory(currency, from_date, to_date))
            elif source == NewsSource.POLYMARKET:
                tasks.append(self._fetch_polymarket(currency, from_date, to_date))
            elif source == NewsSource.DAILYFX:
                tasks.append(self._fetch_dailyfx(currency, from_date, to_date))
            elif source == NewsSource.INVESTING:
                tasks.append(self._fetch_investing(currency, from_date, to_date))
        
        # Gather results
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, list):
                    events.extend(result)
                elif isinstance(result, Exception):
                    logger.warning(f"News fetch error: {result}")
        
        # Cache results
        self._cache[cache_key] = {
            'timestamp': datetime.now(),
            'events': [e.to_dict() for e in events]
        }
        
        # Save to disk
        await self._save_cache(cache_key, events)
        
        return self._filter_events(events, impact_min)
    
    async def get_polymarket_data(
        self,
        currency: str,
        limit: int = 10
    ) -> List[PolymarketEvent]:
        """
        Get Polymarket prediction market data
        
        Polymarket has markets on economic events, elections, and more
        """
        events = []
        
        try:
            # Polymarket API endpoint
            url = "https://polymarket.com/api/markets"
            
            async with self._session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    for market in data.get('markets', []):
                        # Check if market relates to currency
                        market_title = market.get('title', '').lower()
                        currency_keywords = [currency.lower(), f'${currency}', f'{currency}/']
                        
                        if not any(kw in market_title for kw in currency_keywords):
                            # Check description too
                            desc = market.get('description', '').lower()
                            if not any(kw in desc for kw in currency_keywords):
                                continue
                        
                        # Parse outcomes
                        outcomes = {}
                        for outcome in market.get('outcomes', []):
                            outcomes[outcome['name']] = float(outcome['price'])
                        
                        event = PolymarketEvent(
                            event_id=market.get('id', ''),
                            title=market.get('title', ''),
                            description=market.get('description', ''),
                            category=market.get('category', ''),
                            end_date=datetime.fromisoformat(market.get('end_date', datetime.now().isoformat())),
                            outcome_prices=outcomes,
                            volume=float(market.get('volume', 0)),
                            liquidity=float(market.get('liquidity', 0)),
                            open_interest=float(market.get('open_interest', 0)),
                            last_updated=datetime.now()
                        )
                        events.append(event)
                        
                        if len(events) >= limit:
                            break
                            
        except Exception as e:
            logger.error(f"Error fetching Polymarket data: {e}")
        
        return events
    
    async def get_market_sentiment(
        self,
        symbol: str,
        include_prediction_markets: bool = True
    ) -> Optional[MarketSentiment]:
        """
        Get aggregated market sentiment from multiple sources
        
        Args:
            symbol: Trading symbol (e.g., 'EURUSD')
            include_prediction_markets: Include Polymarket data
            
        Returns:
            MarketSentiment object
        """
        # Extract currency from symbol
        if len(symbol) >= 6:
            base = symbol[:3]
            quote = symbol[3:6]
        else:
            base = symbol
            quote = "USD"
        
        # Get news sentiment
        news_events = await self.get_news(
            base,
            from_date=datetime.now() - timedelta(days=7),
            to_date=datetime.now()
        )
        
        news_sentiment = self._calculate_news_sentiment(news_events)
        
        # Get prediction market sentiment if requested
        prediction_sentiment = 0.0
        if include_prediction_markets:
            polymarket_events = await self.get_polymarket_data(base)
            prediction_sentiment = self._calculate_prediction_sentiment(polymarket_events)
        
        # Get social sentiment (would need social media API)
        social_sentiment = 0.0  # Placeholder
        
        # Calculate overall sentiment with weights
        source_weights = {
            'news': 0.4,
            'prediction_markets': 0.3,
            'social': 0.3
        }
        
        overall = (
            news_sentiment * source_weights['news'] +
            prediction_sentiment * source_weights['prediction_markets'] +
            social_sentiment * source_weights['social']
        )
        
        # Confidence based on data availability
        confidence = 0.5
        if news_events:
            confidence += 0.2
        if polymarket_events:
            confidence += 0.3
        
        return MarketSentiment(
            symbol=symbol,
            timestamp=datetime.now(),
            news_sentiment=news_sentiment,
            social_sentiment=social_sentiment,
            prediction_market_sentiment=prediction_sentiment,
            overall_sentiment=overall,
            confidence=min(confidence, 1.0),
            source_weights=source_weights,
            details={
                'news_events': len(news_events),
                'prediction_events': len(polymarket_events) if include_prediction_markets else 0
            }
        )
    
    def _calculate_news_sentiment(self, events: List[NewsEvent]) -> float:
        """Calculate sentiment from news events"""
        if not events:
            return 0.0
        
        sentiment_score = 0
        total_weight = 0
        
        for event in events:
            # Weight by impact
            weight = {
                NewsImpact.HIGH: 3,
                NewsImpact.MEDIUM: 2,
                NewsImpact.LOW: 1
            }.get(event.impact, 1)
            
            # Sentiment value
            sentiment_value = {
                NewsSentiment.POSITIVE: 1,
                NewsSentiment.NEUTRAL: 0,
                NewsSentiment.NEGATIVE: -1
            }.get(event.sentiment, 0)
            
            sentiment_score += sentiment_value * weight
            total_weight += weight
        
        return sentiment_score / total_weight if total_weight > 0 else 0.0
    
    def _calculate_prediction_sentiment(self, events: List[PolymarketEvent]) -> float:
        """Calculate sentiment from prediction markets"""
        if not events:
            return 0.0
        
        sentiment_score = 0
        total_volume = 0
        
        for event in events:
            # Higher volume = more confidence
            volume_weight = min(event.volume / 1000, 1.0)
            
            # Calculate market sentiment from outcomes
            # If there's a "Yes" outcome with high probability, it's positive
            for outcome, price in event.outcome_prices.items():
                if 'yes' in outcome.lower() or 'positive' in outcome.lower():
                    sentiment_score += (price * 2 - 1) * volume_weight
                    total_volume += volume_weight
                    break
        
        return sentiment_score / total_volume if total_volume > 0 else 0.0
    
    def _filter_events(
        self,
        events: List[NewsEvent],
        impact_min: Optional[NewsImpact] = None
    ) -> List[NewsEvent]:
        """Filter events by impact level"""
        if impact_min is None:
            return events
        
        impact_order = {NewsImpact.LOW: 0, NewsImpact.MEDIUM: 1, NewsImpact.HIGH: 2}
        min_level = impact_order.get(impact_min, 0)
        
        return [e for e in events if impact_order.get(e.impact, 0) >= min_level]
    
    async def _fetch_forexfactory(
        self,
        currency: str,
        from_date: datetime,
        to_date: datetime
    ) -> List[NewsEvent]:
        """Fetch from ForexFactory"""
        # Implemented in news_scraper.py
        return []
    
    async def _fetch_polymarket(
        self,
        currency: str,
        from_date: datetime,
        to_date: datetime
    ) -> List[NewsEvent]:
        """Fetch from Polymarket and convert to news events"""
        events = []
        
        try:
            polymarket_events = await self.get_polymarket_data(currency)
            
            for pm_event in polymarket_events:
                # Skip if outside date range
                if pm_event.end_date < from_date or pm_event.end_date > to_date:
                    continue
                
                # Determine sentiment from prediction prices
                sentiment = NewsSentiment.NEUTRAL
                for outcome, price in pm_event.outcome_prices.items():
                    if 'yes' in outcome.lower() or 'positive' in outcome.lower():
                        if price > 0.6:
                            sentiment = NewsSentiment.POSITIVE
                        elif price < 0.4:
                            sentiment = NewsSentiment.NEGATIVE
                        break
                
                # Convert Polymarket event to NewsEvent
                event = NewsEvent(
                    title=f"Polymarket: {pm_event.title}",
                    time=pm_event.end_date,
                    currency=currency,
                    impact=NewsImpact.MEDIUM,
                    sentiment=sentiment,
                    description=f"Prediction market odds: {pm_event.outcome_prices}",
                    source=NewsSource.POLYMARKET,
                    tags=['prediction_market', 'polymarket', pm_event.category],
                    confidence=min(pm_event.liquidity / 10000, 1.0)  # Confidence based on liquidity
                )
                events.append(event)
                
        except Exception as e:
            logger.error(f"Error fetching Polymarket news: {e}")
        
        return events
    
    async def _fetch_dailyfx(
        self,
        currency: str,
        from_date: datetime,
        to_date: datetime
    ) -> List[NewsEvent]:
        """Fetch from DailyFX"""
        # Placeholder - would implement actual scraping
        return []
    
    async def _fetch_investing(
        self,
        currency: str,
        from_date: datetime,
        to_date: datetime
    ) -> List[NewsEvent]:
        """Fetch from Investing.com"""
        # Placeholder - would implement actual scraping
        return []
    
    async def _save_cache(self, key: str, events: List[NewsEvent]):
        """Save cache to disk"""
        try:
            cache_file = self.cache_dir / f"{key.replace('/', '_')}.json"
            data = {
                'timestamp': datetime.now().isoformat(),
                'events': [e.to_dict() for e in events]
            }
            with open(cache_file, 'w') as f:
                json.dump(data, f, default=str)
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")
    
    def get_news_impact(self, event: NewsEvent) -> float:
        """Get numerical impact score for a news event"""
        impact_scores = {
            NewsImpact.HIGH: 3.0,
            NewsImpact.MEDIUM: 2.0,
            NewsImpact.LOW: 1.0
        }
        return impact_scores.get(event.impact, 1.0) * event.confidence
    
    def get_trading_recommendation(
        self,
        symbol: str,
        events: List[NewsEvent]
    ) -> Dict[str, Any]:
        """
        Get trading recommendation based on news events
        
        Returns:
            Dictionary with recommendation, confidence, and reasoning
        """
        if not events:
            return {'action': 'neutral', 'confidence': 0, 'reasoning': 'No news events'}
        
        # Calculate weighted sentiment
        total_score = 0
        total_weight = 0
        reasons = []
        
        for event in events:
            weight = self.get_news_impact(event)
            sentiment_value = {
                NewsSentiment.POSITIVE: 1,
                NewsSentiment.NEUTRAL: 0,
                NewsSentiment.NEGATIVE: -1
            }.get(event.sentiment, 0)
            
            total_score += sentiment_value * weight
            total_weight += weight
            
            if event.sentiment != NewsSentiment.NEUTRAL:
                reasons.append(f"{event.title}: {event.sentiment.value}")
        
        avg_sentiment = total_score / total_weight if total_weight > 0 else 0
        
        # Determine action
        if avg_sentiment > 0.3:
            action = 'buy'
            confidence = min(abs(avg_sentiment), 1.0)
        elif avg_sentiment < -0.3:
            action = 'sell'
            confidence = min(abs(avg_sentiment), 1.0)
        else:
            action = 'neutral'
            confidence = 0.5
        
        return {
            'action': action,
            'confidence': confidence,
            'sentiment_score': avg_sentiment,
            'reasoning': reasons,
            'event_count': len(events)
        }


# Polymarket-specific data source
class PolymarketSource:
    """Specialized Polymarket data source"""
    
    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        self.session = session or aiohttp.ClientSession()
        self.base_url = "https://polymarket.com/api"
        
    async def get_economic_markets(self) -> List[PolymarketEvent]:
        """Get markets related to economic events"""
        events = []
        
        try:
            # Get all markets
            async with self.session.get(f"{self.base_url}/markets") as response:
                if response.status == 200:
                    data = await response.json()
                    
                    for market in data.get('markets', []):
                        # Filter for economic events
                        categories = ['economy', 'finance', 'rates', 'inflation', 'employment']
                        market_category = market.get('category', '').lower()
                        
                        if not any(cat in market_category for cat in categories):
                            continue
                        
                        events.append(self._parse_market(market))
                        
        except Exception as e:
            logger.error(f"Error fetching Polymarket markets: {e}")
        
        return events
    
    async def get_rates_markets(self) -> List[PolymarketEvent]:
        """Get markets related to interest rates"""
        events = []
        
        try:
            async with self.session.get(f"{self.base_url}/markets") as response:
                if response.status == 200:
                    data = await response.json()
                    
                    for market in data.get('markets', []):
                        title = market.get('title', '').lower()
                        
                        # Look for rate-related keywords
                        keywords = ['rate', 'fed', 'interest', 'ecb', 'boe', 'boj']
                        if any(kw in title for kw in keywords):
                            events.append(self._parse_market(market))
                            
        except Exception as e:
            logger.error(f"Error fetching Polymarket rates markets: {e}")
        
        return events
    
    def _parse_market(self, market: Dict) -> PolymarketEvent:
        """Parse raw market data into PolymarketEvent"""
        outcomes = {}
        for outcome in market.get('outcomes', []):
            outcomes[outcome.get('name', 'Unknown')] = float(outcome.get('price', 0))
        
        return PolymarketEvent(
            event_id=market.get('id', ''),
            title=market.get('title', ''),
            description=market.get('description', ''),
            category=market.get('category', ''),
            end_date=datetime.fromisoformat(market.get('end_date', datetime.now().isoformat())),
            outcome_prices=outcomes,
            volume=float(market.get('volume', 0)),
            liquidity=float(market.get('liquidity', 0)),
            open_interest=float(market.get('open_interest', 0)),
            last_updated=datetime.now()
        )
    
    async def close(self):
        """Close the session"""
        await self.session.close()


class NewsCache:
    """Cache for news data to avoid repeated scraping"""
    
    def __init__(self, cache_dir: str = "./news_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache: Dict[str, Dict] = {}
    
    def get(self, key: str) -> Optional[List[Dict]]:
        """Get cached news data"""
        # Check memory cache first
        if key in self._memory_cache:
            data = self._memory_cache[key]
            if datetime.now() - data['timestamp'] < timedelta(hours=1):
                return data['events']
        
        # Check disk cache
        cache_file = self.cache_dir / f"{key}.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                    timestamp = datetime.fromisoformat(data['timestamp'])
                    if datetime.now() - timestamp < timedelta(hours=1):
                        self._memory_cache[key] = data
                        return data['events']
            except Exception:
                pass
        
        return None
    
    def set(self, key: str, events: List[Dict]):
        """Cache news data"""
        data = {
            'timestamp': datetime.now().isoformat(),
            'events': events
        }
        
        # Memory cache
        self._memory_cache[key] = data
        
        # Disk cache
        cache_file = self.cache_dir / f"{key}.json"
        try:
            with open(cache_file, 'w') as f:
                json.dump(data, f, default=str)
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")
    
    def clear(self):
        """Clear cache"""
        self._memory_cache.clear()
        for file in self.cache_dir.glob("*.json"):
            file.unlink()