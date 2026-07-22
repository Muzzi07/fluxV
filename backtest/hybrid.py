import asyncio
import pandas as pd
import numpy as np
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime
import logging

from fluxv.core.strategy import Strategy
from fluxv.core.portfolio import Portfolio
from fluxv.core.types import Bar, Order, Position

logger = logging.getLogger(__name__)


class HybridBacktestEngine:
    """
    Hybrid engine that combines:
    - VectorBT for fast parameter sweeps (ideation)
    - Backtrader for realistic validation (confirmation)
    - Direct simulation for final tuning
    """
    
    def __init__(
        self,
        initial_cash: float = 10000,
        commission: float = 0.001,
        slippage: float = 0.0001
    ):
        self.initial_cash = initial_cash
        self.commission = commission
        self.slippage = slippage
        self.portfolio = Portfolio(initial_cash)
        
        self._results = {}
        self._equity_curve: List[float] = []
        self._trades: List[Dict] = []
    
    async def run_ideation(
        self,
        strategy: Strategy,
        symbols: List[str],
        from_date: datetime,
        to_date: datetime,
        param_ranges: Dict[str, List]
    ) -> Dict:
        """
        Phase 1: Fast ideation using VectorBT-like vectorization
        
        Returns:
            Best parameters and speed metrics
        """
        logger.info("Phase 1: Ideation - Fast vectorized exploration")
        
        # Load data
        data = await self._load_data(symbols, from_date, to_date)
        
        # Vectorized parameter sweep
        results = []
        param_combinations = self._generate_param_grid(param_ranges)
        
        for params in param_combinations:
            # Update strategy params
            strategy.set_params(params)
            
            # Vectorized backtest (fast)
            result = await self._vectorized_backtest(strategy, data)
            results.append({
                'params': params,
                'metrics': result['metrics'],
                'equity_curve': result['equity_curve']
            })
        
        # Find best parameters
        best = max(results, key=lambda x: x['metrics'].get('sharpe_ratio', 0))
        
        logger.info(f"Best parameters: {best['params']} with Sharpe {best['metrics']['sharpe_ratio']:.2f}")
        
        return {
            'best_params': best['params'],
            'best_metrics': best['metrics'],
            'all_results': results,
            'phase': 'ideation'
        }
    
    async def run_validation(
        self,
        strategy: Strategy,
        symbols: List[str],
        from_date: datetime,
        to_date: datetime,
        params: Dict
    ) -> Dict:
        """
        Phase 2: Realistic validation using Backtrader-like event-driven simulation
        
        Returns:
            Realistic performance metrics
        """
        logger.info("Phase 2: Validation - Event-driven realistic simulation")
        
        # Apply best params
        strategy.set_params(params)
        
        # Load data
        data = await self._load_data(symbols, from_date, to_date)
        
        # Event-driven backtest (realistic)
        result = await self._event_driven_backtest(strategy, data)
        
        logger.info(f"Validation complete - Sharpe: {result['metrics']['sharpe_ratio']:.2f}")
        
        return {
            'metrics': result['metrics'],
            'equity_curve': result['equity_curve'],
            'trades': result['trades'],
            'phase': 'validation'
        }
    
    async def run_final(
        self,
        strategy: Strategy,
        symbols: List[str],
        from_date: datetime,
        to_date: datetime
    ) -> Dict:
        """
        Phase 3: Final tuned backtest with full realism
        
        Returns:
            Complete backtest results
        """
        logger.info("Phase 3: Final Tuned Backtest")
        
        # Load data
        data = await self._load_data(symbols, from_date, to_date)
        
        # Full hybrid backtest
        result = await self._hybrid_backtest(strategy, data)
        
        # Generate report
        report = self._generate_report(result)
        
        return {
            **result,
            'report': report,
            'phase': 'final'
        }
    
    async def _load_data(
        self,
        symbols: List[str],
        from_date: datetime,
        to_date: datetime
    ) -> Dict[str, pd.DataFrame]:
        """Load data for all symbols"""
        data = {}
        
        for symbol in symbols:
            # Placeholder - in production, load from data source
            dates = pd.date_range(start=from_date, end=to_date, freq='1h')
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
            data[symbol] = df
        
        return data
    
    async def _vectorized_backtest(
        self,
        strategy: Strategy,
        data: Dict[str, pd.DataFrame]
    ) -> Dict:
        """Vectorized backtest (fast, less realistic)"""
        # Get prices
        prices = pd.DataFrame({
            symbol: df['close'] for symbol, df in data.items()
        })
        
        # Vectorized calculations
        fast_ma = prices.rolling(strategy.fast_ma).mean()
        slow_ma = prices.rolling(strategy.slow_ma).mean()
        
        # Signals
        entries = (fast_ma > slow_ma) & (fast_ma.shift(1) <= slow_ma.shift(1))
        exits = (fast_ma < slow_ma) & (fast_ma.shift(1) >= slow_ma.shift(1))
        
        # Simplified portfolio tracking
        position = np.zeros(len(prices))
        equity = np.zeros(len(prices))
        cash = self.initial_cash
        
        for i in range(len(prices)):
            if entries.iloc[i].any():
                position[i] = 1
            elif exits.iloc[i].any():
                position[i] = 0
            
            # Update equity
            if position[i] == 1:
                equity[i] = cash + prices.iloc[i].sum() * 100000
            else:
                equity[i] = cash
        
        # Calculate metrics
        returns = pd.Series(equity).pct_change().dropna()
        
        metrics = {
            'total_return': (equity[-1] - self.initial_cash) / self.initial_cash * 100,
            'sharpe_ratio': returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0,
            'max_drawdown': self._calculate_max_drawdown(equity),
            'volatility': returns.std() * np.sqrt(252) * 100,
            'total_trades': entries.sum().sum()
        }
        
        return {
            'equity_curve': equity.tolist(),
            'metrics': metrics,
            'trades': []
        }
    
    async def _event_driven_backtest(
        self,
        strategy: Strategy,
        data: Dict[str, pd.DataFrame]
    ) -> Dict:
        """Event-driven backtest (realistic, slower)"""
        
        # Simulate event-driven processing
        timestamps = data[list(data.keys())[0]]['datetime']
        
        equity_curve = []
        trades = []
        portfolio = Portfolio(self.initial_cash)
        
        for i, dt in enumerate(timestamps):
            # Process each symbol
            for symbol, df in data.items():
                bar = df.iloc[i]
                
                # Create bar object
                bar_obj = Bar(
                    time=dt,
                    open=bar['open'],
                    high=bar['high'],
                    low=bar['low'],
                    close=bar['close'],
                    volume=bar['volume']
                )
                
                # Run strategy
                orders = strategy.on_bar(symbol, bar_obj, {})
                if orders:
                    for order in orders:
                        # Execute order with realistic fill
                        filled_order = self._execute_order(
                            order, bar_obj.close, portfolio
                        )
                        if filled_order:
                            trades.append(filled_order)
            
            # Record equity
            equity_curve.append(portfolio.total_equity)
        
        # Calculate metrics
        returns = pd.Series(equity_curve).pct_change().dropna()
        
        metrics = {
            'total_return': (equity_curve[-1] - self.initial_cash) / self.initial_cash * 100,
            'sharpe_ratio': returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0,
            'max_drawdown': self._calculate_max_drawdown(equity_curve),
            'win_rate': len([t for t in trades if t.get('pnl', 0) > 0]) / len(trades) * 100 if trades else 0,
            'total_trades': len(trades)
        }
        
        return {
            'equity_curve': equity_curve,
            'metrics': metrics,
            'trades': trades
        }
    
    async def _hybrid_backtest(
        self,
        strategy: Strategy,
        data: Dict[str, pd.DataFrame]
    ) -> Dict:
        """Hybrid backtest combining vectorized speed with event-driven realism"""
        # Use vectorized for initial screening
        vectorized_result = await self._vectorized_backtest(strategy, data)
        
        # If vectorized looks promising, do event-driven validation
        if vectorized_result['metrics']['sharpe_ratio'] > 0.5:
            event_result = await self._event_driven_backtest(strategy, data)
            return event_result
        
        return vectorized_result
    
    def _execute_order(self, order: Order, price: float, portfolio: Portfolio) -> Dict:
        """Execute order with realistic fill"""
        # Apply slippage
        if order.action == OrderAction.BUY:
            execution_price = price + self.slippage
        else:
            execution_price = price - self.slippage
        
        # Calculate commission
        commission = order.volume * self.commission
        
        # Update portfolio
        if order.action == OrderAction.BUY:
            # Buy
            cost = execution_price * order.volume * 100000 + commission
            if cost <= portfolio.cash:
                portfolio.cash -= cost
                position = Position(
                    ticket=len(portfolio.positions) + 1,
                    symbol=order.symbol,
                    action=OrderAction.BUY,
                    volume=order.volume,
                    price_open=execution_price,
                    price_current=execution_price,
                    sl=order.sl,
                    tp=order.tp,
                    profit=0,
                    comment=order.comment,
                    magic=order.magic,
                    open_time=datetime.now()
                )
                portfolio.add_position(order.symbol, position)
                return {'action': 'BUY', 'price': execution_price, 'volume': order.volume, 'commission': commission}
        else:
            # Sell
            positions = portfolio.positions.get(order.symbol, [])
            if positions:
                position = positions[0]
                pnl = (execution_price - position.price_open) * order.volume * 100000
                portfolio.cash += position.price_open * order.volume * 100000 + pnl - commission
                portfolio.remove_position(order.symbol, position.ticket)
                return {'action': 'SELL', 'price': execution_price, 'volume': order.volume, 'pnl': pnl, 'commission': commission}
        
        return None
    
    def _generate_param_grid(self, param_ranges: Dict[str, List]) -> List[Dict]:
        """Generate parameter grid for optimization"""
        import itertools
        keys = list(param_ranges.keys())
        values = list(param_ranges.values())
        combinations = list(itertools.product(*values))
        return [dict(zip(keys, combo)) for combo in combinations]
    
    def _calculate_max_drawdown(self, equity_curve: List[float]) -> float:
        """Calculate maximum drawdown"""
        if len(equity_curve) < 2:
            return 0
        
        peak = equity_curve[0]
        max_drawdown = 0
        
        for value in equity_curve:
            if value > peak:
                peak = value
            drawdown = (peak - value) / peak * 100 if peak > 0 else 0
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        return max_drawdown
    
    def _generate_report(self, result: Dict) -> Dict:
        """Generate comprehensive backtest report"""
        metrics = result.get('metrics', {})
        
        report = {
            'summary': {
                'total_return': metrics.get('total_return', 0),
                'sharpe_ratio': metrics.get('sharpe_ratio', 0),
                'max_drawdown': metrics.get('max_drawdown', 0),
                'win_rate': metrics.get('win_rate', 0),
                'total_trades': metrics.get('total_trades', 0),
                'total_profit': metrics.get('total_return', 0) / 100 * self.initial_cash
            },
            'risk_metrics': {
                'volatility': metrics.get('volatility', 0),
                'var_95': self._calculate_var(result.get('equity_curve', []), 0.95),
                'sortino_ratio': metrics.get('sortino_ratio', 0)
            },
            'trade_metrics': {
                'avg_profit': metrics.get('avg_profit', 0),
                'profit_factor': metrics.get('profit_factor', 0),
                'avg_win': metrics.get('avg_win', 0),
                'avg_loss': metrics.get('avg_loss', 0)
            }
        }
        
        return report
    
    def _calculate_var(self, equity_curve: List[float], confidence: float) -> float:
        """Calculate Value at Risk"""
        if len(equity_curve) < 2:
            return 0
        
        returns = pd.Series(equity_curve).pct_change().dropna()
        var = returns.quantile(1 - confidence) * 100
        return abs(var)