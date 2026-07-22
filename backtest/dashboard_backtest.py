import asyncio
import pandas as pd
import numpy as np
from typing import Optional, Dict, List, Any
from datetime import datetime
import logging

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    import plotly.io as pio
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

logger = logging.getLogger(__name__)


class BacktestDashboardIntegration:
    """Real-time dashboard for multi-asset backtesting"""
    
    def __init__(self, engine):
        self.engine = engine
        self._running = False
        self._task = None
        self._fig = None
        self._update_interval = 0.5
        self._history = []
        
    async def start(self, update_interval: float = 0.5):
        """Start the dashboard"""
        self._running = True
        self._update_interval = update_interval
        self._task = asyncio.create_task(self._update_loop())
        logger.info("Backtest dashboard started")
    
    async def stop(self):
        """Stop the dashboard"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Backtest dashboard stopped")
    
    async def _update_loop(self):
        """Main update loop"""
        while self._running:
            try:
                if PLOTLY_AVAILABLE:
                    await self._update_figure()
                    await self._display_if_needed()
                await asyncio.sleep(self._update_interval)
            except Exception as e:
                logger.error(f"Dashboard update error: {e}")
    
    async def _update_figure(self):
        """Update the dashboard figure"""
        portfolio = self.engine.portfolio
        
        # Get data
        equity_df = portfolio.get_equity_curve()
        if len(equity_df) < 2:
            return
        
        # Create figure with subplots
        fig = make_subplots(
            rows=3, cols=2,
            subplot_titles=(
                'Portfolio Equity', 'Drawdown',
                'Position Exposure by Symbol', 'Trade P&L Distribution',
                'Performance Metrics', 'Position History'
            ),
            specs=[
                [{"secondary_y": False}, {"secondary_y": False}],
                [{"secondary_y": False}, {"secondary_y": False}],
                [{"colspan": 2}, None]
            ]
        )
        
        # 1. Equity Curve
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
                y=equity_df['cash'],
                name='Cash',
                line=dict(color='green', width=1, dash='dash')
            ),
            row=1, col=1
        )
        
        # 2. Drawdown
        if len(equity_df) > 1:
            peak = equity_df['equity'].expanding().max()
            drawdown = (peak - equity_df['equity']) / peak * 100
            
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
        
        # 3. Position Exposure by Symbol
        positions = portfolio.positions
        if positions:
            exposure_data = []
            symbols = []
            for symbol, pos_list in positions.items():
                total_exposure = sum(p.volume * p.price_current for p in pos_list)
                exposure_data.append(total_exposure)
                symbols.append(symbol)
            
            fig.add_trace(
                go.Bar(
                    x=symbols,
                    y=exposure_data,
                    name='Exposure',
                    marker_color='orange'
                ),
                row=2, col=1
            )
        
        # 4. Trade P&L Distribution
        trades_df = pd.DataFrame(portfolio.trade_history)
        if len(trades_df) > 0:
            fig.add_trace(
                go.Histogram(
                    x=trades_df['profit'],
                    nbinsx=20,
                    name='Trade P&L',
                    marker_color='purple'
                ),
                row=2, col=2
            )
        
        # 5. Performance Metrics
        metrics = portfolio.get_performance_metrics()
        metrics_text = f"""
        <b>Portfolio Metrics</b><br>
        Equity: ${portfolio.total_equity:,.2f}<br>
        Cash: ${portfolio.cash:,.2f}<br>
        Positions: {portfolio.total_positions}<br>
        Exposure: {portfolio.exposure * 100:.1f}%<br>
        Total Return: {metrics.get('total_return', 0):.1f}%<br>
        Sharpe Ratio: {metrics.get('sharpe_ratio', 0):.2f}<br>
        Max Drawdown: {metrics.get('max_drawdown', 0):.1f}%<br>
        """
        
        fig.add_annotation(
            text=metrics_text,
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(size=12),
            align="left",
            row=3, col=1
        )
        
        # Update layout
        fig.update_layout(
            height=900,
            showlegend=True,
            template='plotly_dark',
            title_text=f"Multi-Asset Backtest Dashboard - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        self._fig = fig
    
    async def _display_if_needed(self):
        """Display figure if in notebook or interactive mode"""
        if self._fig and hasattr(self, '_display'):
            self._display(self._fig)
    
    def show(self):
        """Show dashboard in browser"""
        if self._fig and PLOTLY_AVAILABLE:
            self._fig.show()
    
    def save_html(self, filepath: str = "backtest_dashboard.html"):
        """Save dashboard as HTML"""
        if self._fig and PLOTLY_AVAILABLE:
            self._fig.write_html(filepath)
            logger.info(f"Dashboard saved to {filepath}")