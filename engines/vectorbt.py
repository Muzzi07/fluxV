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
    import vectorbt as vbt
    VECTORBT_AVAILABLE = True
except ImportError:
    VECTORBT_AVAILABLE = False
    logging.warning("VectorBT not installed. Install with: pip install vectorbt")

logger = logging.getLogger(__name__)


class VectorBTEngine(BacktestEngine):
    """
    VectorBT-based engine for fast ideation and exploration
    
    Pros:
    - Blazing fast (vectorized operations)
    - Great for parameter optimization
    - Multi-asset support
    
    Cons:
    - Less realistic fill modeling
    - Complex order logic is harder
    """
    
    def __init__(self):
        if not VECTORBT_AVAILABLE:
            raise ImportError("VectorBT not installed")
        
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
        Run VectorBT backtest
        """
        logger.info(f"Running VectorBT backtest for {symbols}")
        
        # Load data for all symbols
        data = {}
        for symbol in symbols:
            # In practice, load from data source
            df = await self._load_data(symbol, from_date, to_date, timeframe)
            data[symbol] = df
        
        # Run vectorized backtest
        self._results = await self._run_vectorized_backtest(
            strategy, data, from_date, to_date
        )
        
        # Extract results
        self._equity_curve = self._extract_equity_curve(self._results)
        self._trades = self._extract_trades(self._results)
        self._metrics = self._calculate_metrics(self._results)
        
        return {
            'equity_curve': self._equity_curve,
            'trades': self._trades,
            'metrics': self._metrics,
            'engine': 'VectorBT'
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
        
        # Generate synthetic data
        np.random.seed(hash(symbol) % 2**32)
        prices = 1.0 + np.cumsum(np.random.normal(0, 0.001, n))
        
        df = pd.DataFrame({
            'Open': prices * (1 + np.random.normal(0, 0.0005, n)),
            'High': prices * (1 + np.abs(np.random.normal(0, 0.001, n))),
            'Low': prices * (1 - np.abs(np.random.normal(0, 0.001, n))),
            'Close': prices,
            'Volume': np.random.randint(100, 1000, n)
        }, index=dates)
        
        return df
    
    async def _run_vectorized_backtest(
        self,
        strategy: Strategy,
        data: Dict[str, pd.DataFrame],
        from_date: datetime,
        to_date: datetime
    ):
        """Run vectorized backtest using VectorBT"""
        
        # This is a simplified version - VectorBT has a rich API
        # for building complex strategies
        
        # Get prices
        prices = pd.DataFrame({
            symbol: df['Close'] for symbol, df in data.items()
        })
        
        # Calculate indicators (vectorized)
        fast_ma = prices.rolling(strategy.fast_ma).mean()
        slow_ma = prices.rolling(strategy.slow_ma).mean()
        
        # Generate signals
        entries = (fast_ma > slow_ma) & (fast_ma.shift(1) <= slow_ma.shift(1))
        exits = (fast_ma < slow_ma) & (fast_ma.shift(1) >= slow_ma.shift(1))
        
        # VectorBT backtest
        portfolio = vbt.Portfolio.from_signals(
            prices,
            entries=entries,
            exits=exits,
            init_cash=10000,
            slippage=0.001
        )
        
        return portfolio
    
    def _extract_equity_curve(self, results) -> List[float]:
        """Extract equity curve from results"""
        if hasattr(results, 'value'):
            return results.value.tolist()
        return []
    
    def _extract_trades(self, results) -> List[Dict]:
        """Extract trade history from results"""
        trades = []
        if hasattr(results, 'trades'):
            for trade in results.trades.records:
                trades.append({
                    'entry_idx': trade.entry_idx,
                    'exit_idx': trade.exit_idx,
                    'size': trade.size,
                    'entry_price': trade.entry_price,
                    'exit_price': trade.exit_price,
                    'pnl': trade.pnl,
                    'trade_return': getattr(trade, 'return')
                })
        return trades
    
    def _calculate_metrics(self, results) -> Dict:
        """Calculate performance metrics"""
        if hasattr(results, 'stats'):
            return {
                'total_return': results.stats().get('Total Return [%]', 0),
                'sharpe_ratio': results.stats().get('Sharpe Ratio', 0),
                'max_drawdown': results.stats().get('Max Drawdown [%]', 0),
                'win_rate': results.stats().get('Win Rate [%]', 0),
                'profit_factor': results.stats().get('Profit Factor', 0),
                'total_trades': results.stats().get('Total Trades', 0)
            }
        return {}
    
    def get_equity_curve(self) -> List[float]:
        return self._equity_curve
    
    def get_trades(self) -> List[Dict]:
        return self._trades
    
    def get_metrics(self) -> Dict:
        return self._metrics


class VectorBTOptimizer:
    """Parameter optimization using VectorBT"""
    
    def __init__(self, engine: VectorBTEngine):
        self.engine = engine
        self.best_params = None
        self.best_score = float('-inf')
    
    async def optimize(
        self,
        strategy_class,
        symbols: List[str],
        param_grid: Dict[str, List],
        from_date: datetime,
        to_date: datetime,
        metric: str = 'sharpe_ratio',
        n_jobs: int = -1
    ) -> Dict:
        """
        Optimize strategy parameters
        
        Args:
            strategy_class: Strategy class
            symbols: Trading symbols
            param_grid: Parameter grid to search
            from_date: Start date
            to_date: End date
            metric: Metric to optimize ('sharpe_ratio', 'total_return', 'win_rate')
            n_jobs: Number of parallel jobs (-1 for all cores)
        """
        logger.info(f"Starting optimization with {len(param_grid)} parameters")
        
        # Generate parameter combinations
        import itertools
        param_keys = list(param_grid.keys())
        param_values = list(param_grid.values())
        combinations = list(itertools.product(*param_values))
        
        logger.info(f"Testing {len(combinations)} parameter combinations")
        
        # Run backtests for each combination
        results = []
        
        for params in combinations:
            param_dict = dict(zip(param_keys, params))
            
            # Create strategy with parameters
            strategy = strategy_class(
                symbols=symbols,
                **param_dict
            )
            
            # Run backtest
            result = await self.engine.run(
                strategy=strategy,
                symbols=symbols,
                from_date=from_date,
                to_date=to_date
            )
            
            score = result['metrics'].get(metric, 0)
            
            results.append({
                'params': param_dict,
                'score': score,
                'result': result
            })
            
            if score > self.best_score:
                self.best_score = score
                self.best_params = param_dict
        
        logger.info(f"Best params: {self.best_params} with {metric}={self.best_score:.4f}")
        
        return {
            'best_params': self.best_params,
            'best_score': self.best_score,
            'results': results
        }