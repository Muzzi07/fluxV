"""
Base engine interface
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime

from fluxV.core.strategy import Strategy
from fluxV.core.portfolio import Portfolio
from fluxV.core.types import Bar, Order, Position


class BacktestEngine(ABC):
    """Base backtest engine interface"""
    
    @abstractmethod
    async def run(
        self,
        strategy: Strategy,
        symbols: List[str],
        from_date: datetime,
        to_date: datetime,
        timeframe: str = '1h'
    ) -> Dict:
        """
        Run backtest
        
        Returns:
            Dict with results
        """
        pass
    
    @abstractmethod
    def get_equity_curve(self) -> List[float]:
        """Get equity curve"""
        pass
    
    @abstractmethod
    def get_trades(self) -> List[Dict]:
        """Get trade history"""
        pass
    
    @abstractmethod
    def get_metrics(self) -> Dict:
        """Get performance metrics"""
        pass