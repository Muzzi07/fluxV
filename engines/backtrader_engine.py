import asyncio
import pandas as pd
import numpy as np
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime
import logging

from fluxV.engines.base import BacktestEngine
from fluxV.core.strategy import Strategy
from fluxV.core.types import Bar, Order, Position, OrderAction

try:
    import backtrader as bt
    BACKTRADER_AVAILABLE = True
except ImportError:
    BACKTRADER_AVAILABLE = False
    logging.warning("Backtrader not installed. Install with: pip install backtrader")

logger = logging.getLogger(__name__)


class BacktraderEngine(BacktestEngine):
    """
    Backtrader-based engine for realistic validation
    
    Pros:
    - Realistic event-driven simulation
    - Rich indicator library
    - Great for multi-asset validation
    
    Cons:
    - Slower than vectorized
    - Complex to optimize
    """
    
    def __init__(self, initial_cash: float = 10000, commission: float = 0.001):
        if not BACKTRADER_AVAILABLE:
            raise ImportError("Backtrader not installed")
        
        self.initial_cash = initial_cash
        self.commission = commission
        self._cerebro = None
        self._equity_curve: List[float] = []
        self._trades: List[Dict] = []
        self._metrics: Dict = {}
        self._results = None
    
    async def run(
        self,
        strategy: Strategy,
        symbols: List[str],
        from_date: datetime,
        to_date: datetime,
        timeframe: str = '1h'
    ) -> Dict:
        """
        Run Backtrader backtest
        """
        logger.info(f"Running Backtrader backtest for {symbols}")
        
        # Create cerebro instance
        self._cerebro = bt.Cerebro()
        
        # Add strategy
        class BacktraderStrategy(bt.Strategy):
            def __init__(self, strategy):
                self.strategy = strategy
                self.bars = {}
                
            def next(self):
                # Process each symbol
                for symbol in symbols:
                    data = self.datas[self.bars[symbol]]
                    if data[0] == data[-1]:  # Check if new bar
                        continue
                    
                    # Create bar object
                    bar = Bar(
                        time=self.datas[0].datetime.datetime(0),
                        open=data.open[0],
                        high=data.high[0],
                        low=data.low[0],
                        close=data.close[0],
                        volume=data.volume[0]
                    )
                    
                    # Run strategy
                    orders = strategy.on_bar(symbol, bar, {'bars': self.bars})
                    if orders:
                        for order in orders:
                            self._execute_order(order, symbol)
            
            def _execute_order(self, order: Order, symbol: str):
                """Execute order"""
                # Get position size
                size = order.volume * 100000  # Standard lot
                
                # Place order
                if order.action == OrderAction.BUY:
                    self.buy(data=self.datas[self.bars[symbol]], size=size)
                else:
                    self.sell(data=self.datas[self.bars[symbol]], size=size)
        
        # Add data feeds
        for symbol in symbols:
            data = await self._load_data(symbol, from_date, to_date, timeframe)
            
            # Convert to Backtrader format
            bt_data = bt.feeds.PandasData(
                dataname=data,
                datetime='datetime',
                open='open',
                high='high',
                low='low',
                close='close',
                volume='volume'
            )
            self._cerebro.adddata(bt_data, name=symbol)
        
        # Add strategy
        self._cerebro.addstrategy(BacktraderStrategy, strategy=strategy)
        
        # Set commission
        self._cerebro.broker.setcommission(commission=self.commission)
        
        # Run backtest
        self._cerebro.run()
        
        # Extract results
        self._equity_curve = self._extract_equity_curve()
        self._trades = self._extract_trades()
        self._metrics = self._calculate_metrics()
        
        return {
            'equity_curve': self._equity_curve,
            'trades': self._trades,
            'metrics': self._metrics,
            'engine': 'Backtrader'
        }
    
    async def _load_data(
        self,
        symbol: str,
        from_date: datetime,
        to_date: datetime,
        timeframe: str
    ) -> pd.DataFrame:
        """Load data for a symbol"""
        # Placeholder - in production, load from data source
        dates = pd.date_range(start=from_date, end=to_date, freq=timeframe)
        n = len(dates)
        
        np.random.seed(hash(symbol) % 2**32)
        prices = 1.0 + np.cumsum(np.random.normal(0, 0.001, n))
        
        df = pd.DataFrame({
            'datetime': dates,
            'open': prices * (1 + np.random.normal(0, 0.0005, n)),
            'high': prices * (1 + np.abs(np.random.normal(0, 0.001, n))),
            'low': prices * (1 - np.abs(np.random.normal(0, 0.001, n))),
            'close': prices,
            'volume': np.random.randint(100, 1000, n)
        })
        
        return df
    
    def _extract_equity_curve(self) -> List[float]:
        """Extract equity curve"""
        if self._cerebro:
            # Get equity values from cerebro
            return [0]  # Placeholder
        return []
    
    def _extract_trades(self) -> List[Dict]:
        """Extract trade history"""
        return []
    
    def _calculate_metrics(self) -> Dict:
        """Calculate performance metrics"""
        if self._cerebro:
            return {
                'final_value': self._cerebro.broker.getvalue(),
                'total_return': (self._cerebro.broker.getvalue() - self.initial_cash) / self.initial_cash * 100,
            }
        return {}
    
    def get_equity_curve(self) -> List[float]:
        return self._equity_curve
    
    def get_trades(self) -> List[Dict]:
        return self._trades
    
    def get_metrics(self) -> Dict:
        return self._metrics