"""
Investing.com data source for fluxV

Scrapes financial data and economic calendar from Investing.com.
"""
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)


class InvestingComSource:
    """Scrape financial data from Investing.com"""

    def __init__(self):
        self.base_url = "https://www.investing.com"
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def get_economic_calendar(
        self,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        limit: int = 50
    ) -> List[Dict]:
        """
        Fetch economic calendar events from Investing.com.

        Args:
            from_date: Start date
            to_date: End date
            limit: Maximum events to return

        Returns:
            List of event dictionaries
        """
        events = []

        try:
            headers = {
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/91.0.4472.124 Safari/537.36'
                ),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            }

            params = {}
            if from_date:
                params['startDate'] = from_date.strftime('%Y-%m-%d')
            if to_date:
                params['endDate'] = to_date.strftime('%Y-%m-%d')

            async with self.session.get(
                f"{self.base_url}/economic-calendar",
                params=params,
                headers=headers
            ) as response:
                if response.status != 200:
                    logger.warning(f"Investing.com returned status {response.status}")
                    return []

                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')

                # Parse events from the calendar table
                table = soup.find('table', id='economicCalendarData')
                if table:
                    rows = table.find_all('tr')[1:]  # Skip header
                    for row in rows[:limit]:
                        try:
                            event = self._parse_event_row(row)
                            if event:
                                events.append(event)
                        except Exception:
                            continue

        except Exception as e:
            logger.error(f"Error scraping Investing.com: {e}")

        return events

    def _parse_event_row(self, row) -> Optional[Dict]:
        """Parse a single calendar event row."""
        try:
            cells = row.find_all('td')
            if len(cells) < 6:
                return None

            return {
                'time': cells[0].text.strip(),
                'country': cells[1].text.strip(),
                'event': cells[2].text.strip(),
                'actual': cells[3].text.strip(),
                'forecast': cells[4].text.strip(),
                'previous': cells[5].text.strip(),
                'sensitivity': cells[6].text.strip() if len(cells) > 6 else '',
            }
        except Exception:
            return None
