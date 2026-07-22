"""
ForexFactory data source for fluxV

Scrapes economic calendar data from ForexFactory.
"""
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import re
import logging

logger = logging.getLogger(__name__)


class ForexFactorySource:
    """Scrape economic calendar data from ForexFactory"""

    def __init__(self):
        self.base_url = "https://www.forexfactory.com/calendar"
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def get_calendar_events(
        self,
        currency: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Fetch economic calendar events from ForexFactory.

        Args:
            currency: Filter by currency (e.g., 'USD', 'EUR')
            from_date: Start date
            to_date: End date
            limit: Maximum events to return

        Returns:
            List of event dictionaries
        """
        events = []

        try:
            params = {}
            if from_date:
                params['day'] = from_date.strftime('%Y-%m-%d')
            if to_date:
                params['end_day'] = to_date.strftime('%Y-%m-%d')
            if currency:
                params['currency'] = currency

            headers = {
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/91.0.4472.124 Safari/537.36'
                )
            }

            async with self.session.get(
                self.base_url,
                params=params,
                headers=headers
            ) as response:
                if response.status != 200:
                    logger.warning(f"ForexFactory returned status {response.status}")
                    return []

                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')

                # Find calendar event rows
                rows = soup.find_all('tr', class_='calendar__row')

                for row in rows[:limit]:
                    try:
                        event = self._parse_event_row(row)
                        if event:
                            events.append(event)
                    except Exception:
                        continue

        except Exception as e:
            logger.error(f"Error scraping ForexFactory: {e}")

        return events

    def _parse_event_row(self, row) -> Optional[Dict]:
        """Parse a single ForexFactory calendar row."""
        try:
            cells = row.find_all('td')
            if len(cells) < 7:
                return None

            # Extract impact level from CSS classes
            impact_cell = row.find('td', class_='calendar__impact')
            impact = 'low'
            if impact_cell:
                span = impact_cell.find('span')
                if span:
                    cls = span.get('class', [])
                    if 'high' in cls:
                        impact = 'high'
                    elif 'medium' in cls:
                        impact = 'medium'

            return {
                'time': cells[0].text.strip() if len(cells) > 0 else '',
                'currency': cells[1].text.strip() if len(cells) > 1 else '',
                'event': cells[2].text.strip() if len(cells) > 2 else '',
                'impact': impact,
                'actual': cells[4].text.strip() if len(cells) > 4 else '',
                'forecast': cells[5].text.strip() if len(cells) > 5 else '',
                'previous': cells[6].text.strip() if len(cells) > 6 else '',
            }
        except Exception:
            return None

    def _parse_float(self, value: str) -> Optional[float]:
        """Parse a string to float, handling various formats."""
        if not value or value == '-' or value == 'N/A':
            return None

        cleaned = re.sub(r'[^\d.-]', '', value)
        try:
            return float(cleaned)
        except ValueError:
            return None
