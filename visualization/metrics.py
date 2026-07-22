import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
from datetime import datetime

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False


class MetricsVisualizer:
    """Visualize performance metrics"""
    
    @staticmethod
    def summary_dashboard(stats: Dict) -> go.Figure:
        """Create summary dashboard"""
        if not PLOTLY_AVAILABLE:
            raise ImportError("Plotly not installed")
        
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=(
                'Key Metrics', 'Monthly Returns',
                'Winners vs Losers', 'Risk Metrics'
            )
        )
        
        # Key metrics table
        metrics_text = f"""
        <b>Performance Summary</b><br>
        Total Return: {stats.get('total_profit', 0):.2f}%<br>
        Sharpe Ratio: {stats.get('sharpe_ratio', 0):.2f}<br>
        Sortino Ratio: {stats.get('sortino_ratio', 0):.2f}<br>
        Calmar Ratio: {stats.get('calmar_ratio', 0):.2f}<br>
        Max Drawdown: {stats.get('max_drawdown', 0):.2f}%<br>
        Win Rate: {stats.get('win_rate', 0):.1f}%<br>
        Profit Factor: {stats.get('profit_factor', 0):.2f}<br>
        Total Trades: {stats.get('total_trades', 0)}
        """
        
        fig.add_annotation(
            text=metrics_text,
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(size=12),
            align="left",
            row=1, col=1
        )
        
        # Monthly returns heatmap
        if 'monthly_returns' in stats:
            monthly = stats['monthly_returns']
            fig.add_trace(
                go.Heatmap(
                    z=monthly.values,
                    x=monthly.columns,
                    y=monthly.index,
                    colorscale='RdYlGn',
                    zmid=0
                ),
                row=1, col=2
            )
        
        # Winners vs Losers
        winners = stats.get('winning_trades', 0)
        losers = stats.get('losing_trades', 0)
        
        fig.add_trace(
            go.Pie(
                labels=['Winners', 'Losers'],
                values=[winners, losers],
                marker_colors=['green', 'red']
            ),
            row=2, col=1
        )
        
        # Risk metrics gauge
        fig.add_trace(
            go.Indicator(
                mode="gauge+number",
                value=stats.get('sharpe_ratio', 0),
                title={'text': "Sharpe Ratio"},
                gauge={
                    'axis': {'range': [None, 3]},
                    'bar': {'color': "darkblue"},
                    'steps': [
                        {'range': [0, 1], 'color': "lightgray"},
                        {'range': [1, 2], 'color': "gray"},
                        {'range': [2, 3], 'color': "darkgray"}
                    ],
                    'threshold': {
                        'line': {'color': "red", 'width': 4},
                        'thickness': 0.75,
                        'value': 1.5
                    }
                }
            ),
            row=2, col=2
        )
        
        fig.update_layout(
            title="Performance Dashboard",
            height=700,
            template="plotly_dark"
        )
        
        return fig
    
    @staticmethod
    def monthly_returns_heatmap(returns: pd.Series) -> go.Figure:
        """Generate monthly returns heatmap"""
        if not PLOTLY_AVAILABLE:
            raise ImportError("Plotly not installed")
        
        # Group by year and month
        monthly = returns.groupby([returns.index.year, returns.index.month]).mean()
        monthly = monthly.unstack()
        
        fig = go.Figure(
            data=go.Heatmap(
                z=monthly.values,
                x=monthly.columns,
                y=monthly.index,
                colorscale='RdYlGn',
                zmid=0,
                text=monthly.round(2).values,
                texttemplate='%{text}%',
                textfont={"size": 10}
            )
        )
        
        fig.update_layout(
            title="Monthly Returns (%)",
            xaxis_title="Month",
            yaxis_title="Year",
            height=500,
            template="plotly_dark"
        )
        
        return fig