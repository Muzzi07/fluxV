"""
Multi-asset backtesting engine for simulating strategies

Contains both the simple BacktestEngine (for single-symbol backtests)
and the MultiAssetBacktestEngine (for multiple symbols with portfolio tracking).
"""
import asyncio
import pandas as pd
import numpy as np
from typing import Optional, List, Dict, Any, Callable, Set
from datetime import datetime, timedelta
from collections import defaultdict
import logging
import time

from fluxV.core.broker import Broker
from fluxV.core.models import Bar, Position, OrderRequest, AccountInfo
from fluxV.core.types import Timeframe, OrderAction
from fluxV.backtest.performance import PerformanceAnalyzer

logger = logging.getLogger(__name__)


# =============================================================================
# Simple BacktestEngine (single-symbol, uses a MockBroker)
# =============================================================================

class BacktestEngine:
    """Backtesting engine for simulating strategies on historical data"""

    def __init__(self, broker: Broker, initial_balance: float = 10000):
        self.broker = broker
        self.initial_balance = initial_balance
        self._bars_processed = 0
        self._callbacks: List[Callable] = []

    async def run(
        self,
        symbol: str,
        timeframe: Timeframe,
        from_date: datetime,
        to_date: datetime,
        strategy_callback: Callable
    ):
        """
        Run backtest on historical data

        Args:
            symbol: Symbol to backtest
            timeframe: Timeframe of data
            from_date: Start date
            to_date: End date
            strategy_callback: Async function called on each bar
        """
        # Load data
        bars = await self.broker.get_rates(symbol, timeframe, from_date, to_date)

        if not bars:
            raise ValueError(f"No data found for {symbol}")

        logger.info(f"Running backtest: {len(bars)} bars from {from_date} to {to_date}")

        # Process each bar
        for i, bar in enumerate(bars):
            # Update current time and price
            if hasattr(self.broker, 'set_current_time'):
                self.broker.set_current_time(bar.time)
            if hasattr(self.broker, 'set_current_price'):
                self.broker.set_current_price(symbol, bar.close)

            # Update positions with current price
            if hasattr(self.broker, 'update_positions'):
                self.broker.update_positions(bar.close)

            # Check stops
            if hasattr(self.broker, 'check_stops'):
                self.broker.check_stops(symbol, bar.high, bar.low)

            # Check pending orders
            if hasattr(self.broker, 'check_pending_orders'):
                self.broker.check_pending_orders(symbol, bar.high, bar.low)

            # Record equity periodically
            if i % 10 == 0 and hasattr(self.broker, 'record_equity'):
                self.broker.record_equity()

            # Call strategy
            await strategy_callback(bar)

            self._bars_processed += 1

        # Final recording
        if hasattr(self.broker, 'record_equity'):
            self.broker.record_equity()

        # Get results
        analyzer = PerformanceAnalyzer(self.broker)
        return analyzer.analyze()

    def add_callback(self, callback: Callable):
        """Add callback for each bar processed"""
        self._callbacks.append(callback)


# =============================================================================
# Portfolio (multi-asset tracking)
# =============================================================================

class Portfolio:
    """Multi-asset portfolio management"""
    
    def __init__(self, initial_capital: float = 10000):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: Dict[str, List[Position]] = defaultdict(list)
        self.equity_curve: List[Dict] = []
        self.trade_history: List[Dict] = []
        self.cash_history: List[float] = []
        self._total_equity = initial_capital
        
    @property
    def total_equity(self) -> float:
        """Calculate total equity including all positions"""
        total_pnl = sum(
            sum(pos.profit for pos in positions)
            for positions in self.positions.values()
        )
        return self.cash + total_pnl
    
    @property
    def total_positions(self) -> int:
        """Total number of positions across all symbols"""
        return sum(len(pos) for pos in self.positions.values())
    
    @property
    def exposure(self) -> float:
        """Total position exposure as percentage of equity"""
        if self.total_equity == 0:
            return 0
        total_volume = sum(
            sum(pos.volume * pos.price_open for pos in positions)
            for positions in self.positions.values()
        )
        return total_volume / self.total_equity

    def add_position(self, symbol: str, position: Position):
        """Add a position to portfolio"""
        self.positions[symbol].append(position)
        
    def remove_position(self, symbol: str, ticket: int):
        """Remove a position from portfolio"""
        self.positions[symbol] = [p for p in self.positions[symbol] if p.ticket != ticket]
        if not self.positions[symbol]:
            del self.positions[symbol]
    
    def update_prices(self, symbol: str, current_price: float):
        """Update position prices for P&L"""
        for position in self.positions.get(symbol, []):
            position.price_current = current_price
            if position.action == OrderAction.BUY:
                position.profit = (current_price - position.price_open) * position.volume
            else:
                position.profit = (position.price_open - current_price) * position.volume
    
    def record_snapshot(self, timestamp: datetime):
        """Record portfolio snapshot for equity curve"""
        equity = self.total_equity
        self.equity_curve.append({
            'time': timestamp,
            'equity': equity,
            'cash': self.cash,
            'positions': self.total_positions,
            'exposure': self.exposure
        })
        self.cash_history.append(self.cash)
    
    def get_equity_curve(self) -> pd.DataFrame:
        """Get equity curve as DataFrame"""
        if not self.equity_curve:
            return pd.DataFrame()
        return pd.DataFrame(self.equity_curve)
    
    def get_performance_metrics(self) -> Dict:
        """Calculate performance metrics"""
        if len(self.equity_curve) < 2:
            return {}
        
        df = self.get_equity_curve()
        returns = df['equity'].pct_change().dropna()
        
        if len(returns) == 0:
            return {}
        
        total_return = (df['equity'].iloc[-1] - df['equity'].iloc[0]) / df['equity'].iloc[0]
        annual_return = total_return * (252 / len(df)) if len(df) > 0 else 0
        volatility = returns.std() * np.sqrt(252)
        sharpe = annual_return / volatility if volatility > 0 else 0
        
        # Drawdown
        peak = df['equity'].expanding().max()
        drawdown = (peak - df['equity']) / peak
        max_drawdown = drawdown.max() * 100
        
        return {
            'total_return': total_return * 100,
            'annual_return': annual_return * 100,
            'sharpe_ratio': sharpe,
            'max_drawdown': max_drawdown,
            'volatility': volatility * 100,
            'total_positions': self.total_positions,
            'current_equity': self.total_equity,
            'current_cash': self.cash,
            'exposure': self.exposure * 100
        }


# =============================================================================
# MultiAssetBacktestEngine (advanced, multi-symbol)
# =============================================================================

class MultiAssetBacktestEngine:
    """
    Multi-asset backtesting engine supporting multiple symbols
    """
    
    def __init__(
        self,
        initial_capital: float = 10000,
        commission: float = 0.001,
        slippage: float = 0.0001,
        data_manager: Optional[Any] = None
    ):
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        self.data_manager = data_manager

        self.portfolio = Portfolio(initial_capital)
        self._bars_processed = 0
        self._pending_orders: Dict[str, List[OrderRequest]] = defaultdict(list)
        self._callbacks: List[Callable] = []
        
        # Dashboard
        self.dashboard = None
        
        # Progress tracking
        self.total_bars = 0
        self.processed_bars = 0
    
    async def run(
        self,
        symbols: List[str],
        timeframe: Timeframe,
        from_date: datetime,
        to_date: datetime,
        strategy_callback: Callable,
        symbols_data: Optional[Dict[str, pd.DataFrame]] = None,
        show_dashboard: bool = False,
        dashboard_interval: float = 0.5
    ):
        """
        Run multi-asset backtest
        
        Args:
            symbols: List of symbols to trade
            timeframe: Timeframe for data
            from_date: Start date
            to_date: End date
            strategy_callback: Async function called for each symbol/bar
            symbols_data: Optional pre-loaded data for symbols
            show_dashboard: Show real-time dashboard
            dashboard_interval: Dashboard update interval
        """
        # Load data for all symbols
        self.total_bars = 0
        symbol_data = {}
        
        for symbol in symbols:
            if symbols_data and symbol in symbols_data:
                df = symbols_data[symbol]
            elif self.data_manager is not None:
                from fluxV.core.types import Timeframe as TF
                df = await self.data_manager.get_rates(
                    symbol, timeframe, from_date, to_date
                )
                if df is None or len(df) == 0:
                    logger.warning(f"No data for {symbol}")
                    continue
            else:
                logger.warning(f"No data manager provided and no data for {symbol}")
                continue

            symbol_data[symbol] = df
            self.total_bars += len(df)
        
        if not symbol_data:
            raise ValueError("No data loaded for any symbol")
        
        # Initialize dashboard
        if show_dashboard:
            try:
                from fluxV.backtest.dashboard_backtest import BacktestDashboardIntegration
                self.dashboard = BacktestDashboardIntegration(self)
                await self.dashboard.start(update_interval=dashboard_interval)
            except ImportError:
                logger.warning("Dashboard dependencies not available. Install plotly.")
                show_dashboard = False

        logger.info(f"Starting backtest with {len(symbol_data)} symbols, {self.total_bars} total bars")
        
        # Get aligned timestamps across all symbols
        timestamps = self._align_timestamps(symbol_data)
        
        # Process each timestamp
        try:
            for idx, timestamp in enumerate(timestamps):
                self.processed_bars = idx
                
                # Get current bars for all symbols
                current_bars = {}
                for symbol, df in symbol_data.items():
                    mask = df['time'] <= timestamp
                    if mask.any():
                        bar_data = df[mask].iloc[-1]
                        bar = Bar(
                            time=bar_data['time'],
                            open=float(bar_data['open']),
                            high=float(bar_data['high']),
                            low=float(bar_data['low']),
                            close=float(bar_data['close']),
                            volume=int(bar_data['volume']) if 'volume' in bar_data else 0
                        )
                        current_bars[symbol] = bar
                
                # Process each symbol
                for symbol, bar in current_bars.items():
                    # Update current price
                    self.portfolio.update_prices(symbol, bar.close)
                    
                    # Check stops for this symbol
                    await self._check_stops(symbol, bar.high, bar.low)
                    
                    # Check pending orders
                    await self._check_pending_orders(symbol, bar)

                    # Call strategy
                    await strategy_callback(
                        symbol=symbol,
                        bar=bar,
                        portfolio=self.portfolio,
                        all_bars=current_bars,
                        news=[]
                    )
                
                # Record portfolio snapshot
                if idx % 10 == 0:
                    self.portfolio.record_snapshot(timestamp)
                    
                # Update progress
                if idx % 100 == 0:
                    progress = (idx / len(timestamps)) * 100
                    logger.info(f"Progress: {progress:.1f}% ({idx}/{len(timestamps)})")
                    
            # Final snapshot
            self.portfolio.record_snapshot(timestamps[-1])
            
        except KeyboardInterrupt:
            logger.info("Backtest interrupted")
        except Exception as e:
            logger.error(f"Backtest error: {e}")
            raise
        finally:
            # Stop dashboard
            if self.dashboard:
                await self.dashboard.stop()
        
        # Generate report
        report = await self.generate_report()
        return report
    
    def _align_timestamps(self, symbol_data: Dict[str, pd.DataFrame]) -> List[datetime]:
        """Align timestamps across all symbols"""
        timestamps = []
        for df in symbol_data.values():
            timestamps.extend(df['time'].tolist())
        return sorted(set(timestamps))
    
    async def _check_stops(self, symbol: str, high: float, low: float):
        """Check stop losses and take profits for a symbol"""
        for position in list(self.portfolio.positions.get(symbol, [])):
            # Check stop loss
            if position.action == OrderAction.BUY:
                if position.sl and low <= position.sl:
                    await self._close_position(symbol, position.ticket, position.sl, "Stop Loss")
                elif position.tp and high >= position.tp:
                    await self._close_position(symbol, position.ticket, position.tp, "Take Profit")
            else:  # SELL
                if position.sl and high >= position.sl:
                    await self._close_position(symbol, position.ticket, position.sl, "Stop Loss")
                elif position.tp and low <= position.tp:
                    await self._close_position(symbol, position.ticket, position.tp, "Take Profit")
    
    async def _check_pending_orders(self, symbol: str, bar: Bar):
        """Check if pending orders should be triggered"""
        if symbol not in self._pending_orders:
            return
        
        triggered = []
        for order in self._pending_orders[symbol]:
            if order.order_type == OrderType.LIMIT:
                if order.action == OrderAction.BUY and bar.low <= order.price:
                    triggered.append(order)
                elif order.action == OrderAction.SELL and bar.high >= order.price:
                    triggered.append(order)
            elif order.order_type == OrderType.STOP:
                if order.action == OrderAction.BUY and bar.high >= order.price:
                    triggered.append(order)
                elif order.action == OrderAction.SELL and bar.low <= order.price:
                    triggered.append(order)
        
        for order in triggered:
            await self._execute_pending_order(symbol, order, bar.close)
    
    async def _execute_pending_order(self, symbol: str, order: OrderRequest, current_price: float):
        """Execute a pending order"""
        position = await self._open_position(
            symbol=symbol,
            action=order.action,
            volume=order.volume,
            price=current_price,
            sl=order.sl,
            tp=order.tp,
            comment=f"Pending Order: {order.comment or ''}"
        )
        if position:
            self.portfolio.add_position(symbol, position)
        self._pending_orders[symbol].remove(order)

    async def _open_position(
        self,
        symbol: str,
        action: OrderAction,
        volume: float,
        price: float,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        comment: Optional[str] = None,
        magic: Optional[int] = None
    ) -> Optional[Position]:
        """Open a new position"""
        # Apply slippage
        if action == OrderAction.BUY:
            execution_price = price + self.slippage
        else:
            execution_price = price - self.slippage
        
        # Calculate margin required
        margin_required = execution_price * volume * 0.01  # 1% margin
        if margin_required > self.portfolio.cash:
            logger.warning(f"Insufficient cash for {symbol} position")
            return None
        
        # Create position
        position = Position(
            ticket=int(time.time() * 1000) + len(self.portfolio.positions.get(symbol, [])),
            symbol=symbol,
            action=action,
            volume=volume,
            price_open=execution_price,
            price_current=execution_price,
            sl=sl,
            tp=tp,
            profit=0,
            comment=comment,
            magic=magic,
            open_time=datetime.now(),
            commission=volume * self.commission
        )
        
        # Deduct commission and margin
        self.portfolio.cash -= margin_required + position.commission
        
        return position
    
    async def _close_position(self, symbol: str, ticket: int, price: float, reason: str):
        """Close a position"""
        positions = self.portfolio.positions.get(symbol, [])
        position = next((p for p in positions if p.ticket == ticket), None)
        
        if not position:
            return
        
        # Calculate profit
        if position.action == OrderAction.BUY:
            profit = (price - position.price_open) * position.volume
        else:
            profit = (position.price_open - price) * position.volume
        
        # Add back margin
        margin_required = position.price_open * position.volume * 0.01
        self.portfolio.cash += margin_required
        
        # Add profit/loss
        self.portfolio.cash += profit
        
        # Record trade
        self.portfolio.trade_history.append({
            'ticket': ticket,
            'symbol': symbol,
            'action': position.action.value,
            'volume': position.volume,
            'price_open': position.price_open,
            'price_close': price,
            'profit': profit,
            'commission': position.commission,
            'open_time': position.open_time,
            'close_time': datetime.now(),
            'close_reason': reason,
            'bars_held': (datetime.now() - position.open_time).total_seconds() / 3600
        })
        
        # Remove from portfolio
        self.portfolio.remove_position(symbol, ticket)
        
        logger.info(f"Closed {symbol} position {ticket}: {reason} - Profit: ${profit:.2f}")
    
    async def generate_report(self) -> Dict:
        """Generate comprehensive backtest report"""
        df = self.portfolio.get_equity_curve()
        
        if len(df) == 0:
            return {'error': 'No data available'}
        
        # Calculate metrics
        metrics = self.portfolio.get_performance_metrics()
        
        # Trade statistics
        trades_df = pd.DataFrame(self.portfolio.trade_history)
        
        if len(trades_df) > 0:
            winners = trades_df[trades_df['profit'] > 0]
            losers = trades_df[trades_df['profit'] < 0]
            
            avg_win = winners['profit'].mean() if len(winners) > 0 else 0
            avg_loss = losers['profit'].mean() if len(losers) > 0 else 0
            win_rate = len(winners) / len(trades_df) * 100
            profit_factor = abs(winners['profit'].sum() / losers['profit'].sum()) if len(losers) > 0 and losers['profit'].sum() != 0 else 0
            
            metrics.update({
                'total_trades': len(trades_df),
                'winning_trades': len(winners),
                'losing_trades': len(losers),
                'win_rate': win_rate,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
                'profit_factor': profit_factor,
                'best_trade': trades_df['profit'].max() if len(trades_df) > 0 else 0,
                'worst_trade': trades_df['profit'].min() if len(trades_df) > 0 else 0,
            })
        
        # Symbol breakdown
        symbol_performance = {}
        if len(trades_df) > 0:
            for symbol_name in trades_df['symbol'].unique():
                symbol_trades = trades_df[trades_df['symbol'] == symbol_name]
                symbol_performance[symbol_name] = {
                    'total_trades': len(symbol_trades),
                    'profit': float(symbol_trades['profit'].sum()),
                    'win_rate': float(len(symbol_trades[symbol_trades['profit'] > 0]) / len(symbol_trades) * 100)
                }
        
        report = {
            **metrics,
            'total_bars': self.total_bars,
            'processed_bars': self.processed_bars,
            'symbol_performance': symbol_performance,
            'equity_curve': df,
            'trade_history': trades_df,
            'initial_capital': self.initial_capital,
            'final_equity': self.portfolio.total_equity,
            'total_return_pct': ((self.portfolio.total_equity - self.initial_capital) / self.initial_capital) * 100
        }
        
        return report