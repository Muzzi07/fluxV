import asyncio
import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import re
import json
import logging
from pathlib import Path

from fluxV.data.news import NewsEvent, NewsImpact, NewsSentiment

logger = logging.getLogger(__name__)


class NewsScraper:
    """Scrape news data from financial websites"""
    
    def __init__(self):
        self.session = None
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def scrape_forexfactory(
        self,
        currency: str,
        from_date: datetime,
        to_date: datetime
    ) -> List[NewsEvent]:
        """Scrape news from ForexFactory"""
        events = []
        
        try:
            # ForexFactory calendar URL
            base_url = "https://www.forexfactory.com/calendar"
            
            # Build query parameters
            params = {
                'day': from_date.strftime('%Y-%m-%d'),
                'end_day': to_date.strftime('%Y-%m-%d')
            }
            
            if currency:
                params['currency'] = currency
            
            async with self.session.get(
                base_url,
                params=params,
                headers={'User-Agent': self.user_agent}
            ) as response:
                if response.status != 200:
                    logger.warning(f"ForexFactory returned status {response.status}")
                    return []
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Parse calendar events
                calendar_rows = soup.find_all('tr', class_='calendar__row')
                
                for row in calendar_rows:
                    try:
                        event = self._parse_forexfactory_row(row)
                        if event and from_date <= event.time <= to_date:
                            events.append(event)
                    except Exception as e:
                        continue
                        
        except Exception as e:
            logger.error(f"Error scraping ForexFactory: {e}")
        
        return events
    
    def _parse_forexfactory_row(self, row) -> Optional[NewsEvent]:
        """Parse a ForexFactory calendar row"""
        try:
            # Extract time
            time_elem = row.find('td', class_='calendar__time')
            if not time_elem:
                return None
            
            # Extract currency
            currency_elem = row.find('td', class_='calendar__currency')
            if not currency_elem:
                return None
            
            # Extract impact
            impact_elem = row.find('td', class_='calendar__impact')
            impact = NewsImpact.LOW
            if impact_elem:
                if 'high' in impact_elem.get('class', []):
                    impact = NewsImpact.HIGH
                elif 'medium' in impact_elem.get('class', []):
                    impact = NewsImpact.MEDIUM
            
            # Extract title/event
            title_elem = row.find('td', class_='calendar__event')
            title = title_elem.text.strip() if title_elem else ""
            
            # Extract actual, forecast, previous
            actual_elem = row.find('td', class_='calendar__actual')
            forecast_elem = row.find('td', class_='calendar__forecast')
            previous_elem = row.find('td', class_='calendar__previous')
            
            actual = self._parse_float(actual_elem.text.strip()) if actual_elem else None
            forecast = self._parse_float(forecast_elem.text.strip()) if forecast_elem else None
            previous = self._parse_float(previous_elem.text.strip()) if previous_elem else None
            
            # Determine sentiment
            sentiment = NewsSentiment.NEUTRAL
            if actual is not None and forecast is not None:
                if actual > forecast:
                    sentiment = NewsSentiment.POSITIVE
                elif actual < forecast:
                    sentiment = NewsSentiment.NEGATIVE
            
            return NewsEvent(
                title=title,
                time=datetime.now(),  # Need to parse time properly
                currency=currency_elem.text.strip(),
                impact=impact,
                actual=actual,
                forecast=forecast,
                previous=previous,
                sentiment=sentiment,
                source="ForexFactory"
            )
            
        except Exception as e:
            return None
    
    def _parse_float(self, value: str) -> Optional[float]:
        """Parse a string to float, handling various formats"""
        if not value or value == '-' or value == 'N/A':
            return None
        
        # Remove non-numeric characters except decimal
        cleaned = re.sub(r'[^\d.-]', '', value)
        try:
            return float(cleaned)
        except ValueError:
            return None


class NewsCache:
    """Cache for news data to avoid repeated scraping"""
    
    def __init__(self, cache_dir: str = "./news_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def get(self, key: str) -> Optional[List[Dict]]:
        """Get cached news data"""
        cache_file = self.cache_dir / f"{key}.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    return json.load(f)
            except Exception:
                return None
        return None
    
    def set(self, key: str, data: List[Dict]):
        """Cache news data"""
        cache_file = self.cache_dir / f"{key}.json"
        with open(cache_file, 'w') as f:
            json.dump(data, f, default=str)