from abc import ABC, abstractmethod
from typing import Optional, List
from datetime import datetime

from fluxV.core.broker import Broker
from fluxV.core.models import Bar, Position, OrderRequest
from fluxV.core.types import Timeframe


class BaseStrategy(ABC):
    """Base class for all trading strategies"""
    
    def __init__(
        self,
        broker: Broker,
        symbol: str,
        timeframe: Timeframe,
        volume: float = 0.1,
        max_positions: int = 1
    ):
        self.broker = broker
        self.symbol = symbol
        self.timeframe = timeframe
        self.volume = volume
        self.max_positions = max_positions
        self.is_running = False
        self._positions: List[Position] = []
    
    @abstractmethod
    async def on_bar(self, bar: Bar) -> Optional[OrderRequest]:
        """
        Called on each new bar.
        Returns OrderRequest if a trade should be placed.
        """
        pass
    
    @abstractmethod
    async def on_tick(self, tick) -> Optional[OrderRequest]:
        """
        Called on each tick.
        Returns OrderRequest if a trade should be placed.
        """
        pass
    
    async def before_start(self):
        """Called before strategy starts"""
        pass
    
    async def after_stop(self):
        """Called after strategy stops"""
        pass
    
    async def on_position_opened(self, position: Position):
        """Called when a position is opened"""
        pass
    
    async def on_position_closed(self, position: Position):
        """Called when a position is closed"""
        pass
    
    async def get_positions(self) -> List[Position]:
        """Get current positions for this strategy's symbol"""
        return await self.broker.get_positions(self.symbol)
    
    async def close_all(self):
        """Close all positions"""
        await self.broker.close_all_positions(self.symbol)
    
    def get_indicators(self):
        """Get indicators for the strategy (override in subclasses)"""
        return {}