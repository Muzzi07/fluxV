import asyncio
import pandas as pd
import numpy as np
from typing import Optional, Dict, List, Any
from datetime import datetime
from dataclasses import dataclass, field
import logging

from fluxV.core.broker import Broker
from fluxV.core.models import Position, Bar, AccountInfo

logger = logging.getLogger(__name__)

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    import plotly.io as pio
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    logger.warning("Plotly not installed. Install with: pip install plotly")


@dataclass
class DashboardMetrics:
    """Real-time dashboard metrics"""
    timestamp: datetime
    balance: float
    equity: float
    profit: float
    positions: int
    win_rate: float
    total_trades: int
    current_drawdown: float
    max_drawdown: float
    sharpe_ratio: float
    avg_trade: float
    profit_factor: float


class Dashboard:
    """Base dashboard class for real-time visualization"""
    
    def __init__(
        self,
        broker: Broker,
        update_interval: float = 1.0,
        max_history: int = 1000
    ):
        self.broker = broker
        self.update_interval = update_interval
        self.max_history = max_history
        
        self._metrics_history: List[DashboardMetrics] = []
        self._equity_history: List[float] = []
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
        self._fig = None
    
    async def start(self):
        """Start the dashboard"""
        self._running = True
        self._task = asyncio.create_task(self._update_loop())
        logger.info("Dashboard started")
    
    async def stop(self):
        """Stop the dashboard"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Dashboard stopped")
    
    async def _update_loop(self):
        """Main update loop"""
        while self._running:
            try:
                await self._update_metrics()
                await self._update_display()
                await asyncio.sleep(self.update_interval)
            except Exception as e:
                logger.error(f"Dashboard update error: {e}")
    
    async def _update_metrics(self):
        """Update dashboard metrics"""
        try:
            account = await self.broker.get_account_info()
            positions = await self.broker.get_positions()
            
            # Get performance metrics from broker
            stats = {}
            if hasattr(self.broker, 'get_stats'):
                stats = self.broker.get_stats()
            
            metrics = DashboardMetrics(
                timestamp=datetime.now(),
                balance=account.balance,
                equity=account.equity,
                profit=account.profit,
                positions=len(positions),
                win_rate=stats.get('win_rate', 0),
                total_trades=stats.get('total_trades', 0),
                current_drawdown=0,
                max_drawdown=stats.get('max_drawdown', 0),
                sharpe_ratio=stats.get('sharpe_ratio', 0),
                avg_trade=stats.get('avg_trade', 0),
                profit_factor=stats.get('profit_factor', 0)
            )
            
            self._metrics_history.append(metrics)
            if len(self._metrics_history) > self.max_history:
                self._metrics_history = self._metrics_history[-self.max_history:]
            
            self._equity_history.append(metrics.equity)
            if len(self._equity_history) > self.max_history:
                self._equity_history = self._equity_history[-self.max_history:]
                
        except Exception as e:
            logger.error(f"Error updating metrics: {e}")
    
    async def _update_display(self):
        """Update the display (override in subclasses)"""
        pass
    
    def get_latest_metrics(self) -> Optional[DashboardMetrics]:
        """Get the latest metrics"""
        return self._metrics_history[-1] if self._metrics_history else None


class BacktestDashboard(Dashboard):
    """Backtest dashboard with comprehensive visualizations"""
    
    def __init__(
        self,
        broker: Broker,
        update_interval: float = 0.5,
        max_history: int = 1000,
        show_plot: bool = True
    ):
        super().__init__(broker, update_interval, max_history)
        self.show_plot = show_plot
        self._position_history: List[Dict] = []
        self._trade_history: List[Dict] = []
        self._bars_processed = 0
        self._start_time = datetime.now()
        
        if show_plot and not PLOTLY_AVAILABLE:
            logger.warning("Plotly not available. Install with: pip install plotly")
            self.show_plot = False
    
    async def _update_display(self):
        """Update the plotly dashboard"""
        if not self.show_plot or not PLOTLY_AVAILABLE:
            return
        
        if len(self._equity_history) < 2:
            return
        
        # Create subplot figure
        fig = make_subplots(
            rows=3, cols=2,
            subplot_titles=(
                'Equity Curve', 'Drawdown',
                'Position P&L', 'Trade Distribution',
                'Performance Metrics', 'Position History'
            ),
            specs=[
                [{"secondary_y": False}, {"secondary_y": False}],
                [{"secondary_y": False}, {"secondary_y": False}],
                [{"colspan": 2}, None]
            ]
        )
        
        # 1. Equity Curve
        equity_df = pd.DataFrame({
            'time': [m.timestamp for m in self._metrics_history],
            'equity': [m.equity for m in self._metrics_history],
            'balance': [m.balance for m in self._metrics_history]
        })
        
        fig.add_trace(
            go.Scatter(
                x=equity_df['time'],
                y=equity_df['equity'],
                name='Equity',
                line=dict(color='blue', width=2)
            ),
            row=1, col=1
        )
        
        fig.add_trace(
            go.Scatter(
                x=equity_df['time'],
                y=equity_df['balance'],
                name='Balance',
                line=dict(color='green', width=1, dash='dash')
            ),
            row=1, col=1
        )
        
        # 2. Drawdown
        if len(self._equity_history) > 1:
            peak = np.maximum.accumulate(self._equity_history)
            drawdown = (peak - self._equity_history) / peak * 100
            
            fig.add_trace(
                go.Scatter(
                    x=equity_df['time'],
                    y=drawdown,
                    name='Drawdown %',
                    fill='tozeroy',
                    line=dict(color='red', width=1)
                ),
                row=1, col=2
            )
        
        # 3. Position P&L
        positions = await self.broker.get_positions()
        if positions:
            pnl_data = [p.profit for p in positions]
            symbols = [p.symbol for p in positions]
            
            fig.add_trace(
                go.Bar(
                    x=symbols,
                    y=pnl_data,
                    name='P&L by Symbol',
                    marker_color=['green' if p > 0 else 'red' for p in pnl_data]
                ),
                row=2, col=1
            )
        
        # 4. Trade Distribution
        if hasattr(self.broker, 'get_trade_history'):
            trades = self.broker.get_trade_history()
            if len(trades) > 0:
                profits = trades['profit'].tolist()
                
                fig.add_trace(
                    go.Histogram(
                        x=profits,
                        name='Trade Profit Distribution',
                        nbinsx=20,
                        marker_color='purple'
                    ),
                    row=2, col=2
                )
        
        # 5. Performance Metrics
        metrics = self.get_latest_metrics()
        if metrics:
            metrics_text = f"""
            <b>Performance Metrics</b><br>
            Balance: ${metrics.balance:,.2f}<br>
            Equity: ${metrics.equity:,.2f}<br>
            Total Profit: ${metrics.profit:,.2f}<br>
            Total Trades: {metrics.total_trades}<br>
            Win Rate: {metrics.win_rate:.1f}%<br>
            Max Drawdown: {metrics.max_drawdown:.2f}%<br>
            Sharpe Ratio: {metrics.sharpe_ratio:.2f}<br>
            Profit Factor: {metrics.profit_factor:.2f}<br>
            Avg Trade: ${metrics.avg_trade:.2f}<br>
            Positions: {metrics.positions}
            """
            
            fig.add_annotation(
                text=metrics_text,
                xref="paper", yref="paper",
                x=0.5, y=0.5,
                showarrow=False,
                font=dict(size=12),
                align="left"
            )
        
        # Update layout
        fig.update_layout(
            height=900,
            showlegend=True,
            template='plotly_dark',
            title_text=f"Backtest Dashboard - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        fig.update_xaxes(title_text="Time", row=1, col=1)
        fig.update_xaxes(title_text="Time", row=1, col=2)
        fig.update_xaxes(title_text="Symbol", row=2, col=1)
        fig.update_xaxes(title_text="Profit", row=2, col=2)
        
        self._fig = fig
    
    def show(self, port: int = 8050):
        """Show dashboard in browser"""
        if self._fig and PLOTLY_AVAILABLE:
            self._fig.show()
        else:
            logger.warning("No figure to display")
    
    def save_html(self, filepath: str = "dashboard.html"):
        """Save dashboard as HTML"""
        if self._fig and PLOTLY_AVAILABLE:
            self._fig.write_html(filepath)
            logger.info(f"Dashboard saved to {filepath}")
    
    def get_dataframe(self) -> pd.DataFrame:
        """Get metrics as DataFrame"""
        if not self._metrics_history:
            return pd.DataFrame()
        
        return pd.DataFrame([
            {
                'timestamp': m.timestamp,
                'balance': m.balance,
                'equity': m.equity,
                'profit': m.profit,
                'positions': m.positions,
                'win_rate': m.win_rate,
                'total_trades': m.total_trades,
                'drawdown': m.current_drawdown,
                'max_drawdown': m.max_drawdown,
                'sharpe_ratio': m.sharpe_ratio,
                'avg_trade': m.avg_trade,
                'profit_factor': m.profit_factor
            }
            for m in self._metrics_history
        ])