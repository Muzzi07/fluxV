import asyncio
import MetaTrader5 as mt5
from typing import Optional, AsyncIterator, Callable, Awaitable
from datetime import datetime

from fluxV.core.models import Bar, Tick, MarketSnapshot
from fluxV.core.types import Timeframe
from fluxV.core.exceptions import SymbolNotFoundError


class DataStream:
    """Streams real-time data from MT5"""
    
    def __init__(self):
        self._streaming = False
        self._tasks = []
    
    async def stream_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        callback: Optional[Callable[[Bar], Awaitable[None]]] = None
    ) -> AsyncIterator[Bar]:
        """Stream real-time bars"""
        loop = asyncio.get_event_loop()
        
        # Get initial bar
        rates = await loop.run_in_executor(
            None, mt5.copy_rates_from_pos, symbol, timeframe.value, 0, 1
        )
        if rates is None or len(rates) == 0:
            raise SymbolNotFoundError(f"No data for {symbol}")
        
        current_time = datetime.fromtimestamp(rates[0][0])
        self._streaming = True
        
        try:
            while self._streaming:
                rates = await loop.run_in_executor(
                    None, mt5.copy_rates_from_pos, symbol, timeframe.value, 0, 2
                )
                
                if rates is not None and len(rates) >= 2:
                    bar_time = datetime.fromtimestamp(rates[-1][0])
                    if bar_time > current_time:
                        bar = self._convert_to_bar(rates[-1])
                        current_time = bar_time
                        
                        if callback:
                            await callback(bar)
                        yield bar
                
                await asyncio.sleep(1)
                
        except asyncio.CancelledError:
            self._streaming = False
            raise
    
    async def stream_ticks(
        self,
        symbol: str,
        callback: Optional[Callable[[Tick], Awaitable[None]]] = None
    ) -> AsyncIterator[Tick]:
        """Stream real-time ticks"""
        loop = asyncio.get_event_loop()
        self._streaming = True
        last_time = None
        
        try:
            while self._streaming:
                tick = await loop.run_in_executor(None, mt5.symbol_info_tick, symbol)
                
                if tick:
                    tick_time = datetime.fromtimestamp(tick.time)
                    if last_time is None or tick_time > last_time:
                        last_time = tick_time
                        tick_obj = Tick(
                            time=tick_time,
                            bid=tick.bid,
                            ask=tick.ask,
                            last=tick.last,
                            volume=tick.volume,
                            flags=tick.flags
                        )
                        
                        if callback:
                            await callback(tick_obj)
                        yield tick_obj
                
                await asyncio.sleep(0.1)
                
        except asyncio.CancelledError:
            self._streaming = False
            raise
    
    def _convert_to_bar(self, rate) -> Bar:
        """Convert MT5 rate to Bar"""
        return Bar(
            time=datetime.fromtimestamp(rate[0]),
            open=rate[1],
            high=rate[2],
            low=rate[3],
            close=rate[4],
            volume=int(rate[5]) if rate[5] else 0
        )
    
    def stop(self):
        """Stop streaming"""
        self._streaming = False
        for task in self._tasks:
            task.cancel()