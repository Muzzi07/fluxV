"""
DailyFX data source for fluxV

Scrapes economic calendar and analysis from DailyFX.
"""
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)


class DailyFXSource:
    """Scrape economic calendar data from DailyFX"""

    def __init__(self):
        self.base_url = "https://www.dailyfx.com/economic-calendar"
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
        limit: int = 50
    ) -> List[Dict]:
        """
        Fetch economic calendar events from DailyFX.

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
            headers = {
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/91.0.4472.124 Safari/537.36'
                )
            }

            async with self.session.get(
                self.base_url,
                headers=headers
            ) as response:
                if response.status != 200:
                    logger.warning(f"DailyFX returned status {response.status}")
                    return []

                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')

                # Parse calendar events from the page
                # (DailyFX uses JavaScript rendering, so this is a basic parser)
                event_elements = soup.find_all('tr', class_='calendar-row')

                for elem in event_elements[:limit]:
                    try:
                        event = self._parse_event_row(elem)
                        if event:
                            events.append(event)
                    except Exception:
                        continue

        except Exception as e:
            logger.error(f"Error scraping DailyFX: {e}")

        return events

    def _parse_event_row(self, row) -> Optional[Dict]:
        """Parse a single calendar event row."""
        try:
            cells = row.find_all('td')
            if len(cells) < 5:
                return None

            return {
                'time': cells[0].text.strip(),
                'currency': cells[1].text.strip(),
                'event': cells[2].text.strip(),
                'impact': cells[3].text.strip(),
                'actual': cells[4].text.strip() if len(cells) > 4 else None,
                'forecast': cells[5].text.strip() if len(cells) > 5 else None,
                'previous': cells[6].text.strip() if len(cells) > 6 else None,
            }
        except Exception:
            return None
