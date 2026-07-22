from typing import Optional, List, Dict, Any
from datetime import datetime
import pandas as pd
import numpy as np
from enum import Enum

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    import plotly.express as px
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False


class PlotType(Enum):
    """Plot types"""
    LINE = "line"
    BAR = "bar"
    CANDLESTICK = "candlestick"
    SCATTER = "scatter"
    HISTOGRAM = "histogram"
    HEATMAP = "heatmap"


class ChartGenerator:
    """Generate trading charts"""
    
    @staticmethod
    def candlestick_chart(
        df: pd.DataFrame,
        title: str = "Price Chart",
        show_volume: bool = True,
        indicators: Optional[List[Dict]] = None
    ) -> go.Figure:
        """
        Generate candlestick chart with optional indicators
        
        Args:
            df: DataFrame with time, open, high, low, close columns
            title: Chart title
            show_volume: Show volume subplot
            indicators: List of indicators to overlay
        """
        if not PLOTLY_AVAILABLE:
            raise ImportError("Plotly not installed")
        
        rows = 2 if show_volume else 1
        fig = make_subplots(
            rows=rows, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            row_heights=[0.8, 0.2] if show_volume else [1]
        )
        
        # Candlestick
        fig.add_trace(
            go.Candlestick(
                x=df['time'],
                open=df['open'],
                high=df['high'],
                low=df['low'],
                close=df['close'],
                name='Price'
            ),
            row=1, col=1
        )
        
        # Add indicators
        if indicators:
            for indicator in indicators:
                fig.add_trace(
                    go.Scatter(
                        x=df['time'],
                        y=indicator['data'],
                        name=indicator['name'],
                        line=indicator.get('line', {})
                    ),
                    row=1, col=1
                )
        
        # Volume
        if show_volume and 'volume' in df.columns:
            colors = ['green' if close >= open else 'red' 
                     for close, open in zip(df['close'], df['open'])]
            
            fig.add_trace(
                go.Bar(
                    x=df['time'],
                    y=df['volume'],
                    name='Volume',
                    marker_color=colors,
                    opacity=0.5
                ),
                row=2, col=1
            )
        
        fig.update_layout(
            title=title,
            xaxis_title="Time",
            yaxis_title="Price",
            template="plotly_dark",
            height=800,
            xaxis_rangeslider_visible=False
        )
        
        return fig
    
    @staticmethod
    def equity_curve(
        equity: List[float],
        timestamps: List[datetime],
        benchmark: Optional[List[float]] = None,
        title: str = "Equity Curve"
    ) -> go.Figure:
        """Generate equity curve chart"""
        if not PLOTLY_AVAILABLE:
            raise ImportError("Plotly not installed")
        
        fig = go.Figure()
        
        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=equity,
                name='Equity',
                line=dict(color='blue', width=2),
                fill='tozeroy',
                fillcolor='rgba(0,0,255,0.1)'
            )
        )
        
        if benchmark:
            fig.add_trace(
                go.Scatter(
                    x=timestamps,
                    y=benchmark,
                    name='Benchmark',
                    line=dict(color='gray', width=1, dash='dash')
                )
            )
        
        fig.update_layout(
            title=title,
            xaxis_title="Time",
            yaxis_title="Equity",
            template="plotly_dark",
            height=500
        )
        
        return fig
    
    @staticmethod
    def drawdown_chart(
        drawdown: List[float],
        timestamps: List[datetime],
        title: str = "Drawdown"
    ) -> go.Figure:
        """Generate drawdown chart"""
        if not PLOTLY_AVAILABLE:
            raise ImportError("Plotly not installed")
        
        fig = go.Figure()
        
        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=drawdown,
                name='Drawdown %',
                fill='tozeroy',
                line=dict(color='red', width=1),
                fillcolor='rgba(255,0,0,0.2)'
            )
        )
        
        fig.update_layout(
            title=title,
            xaxis_title="Time",
            yaxis_title="Drawdown %",
            template="plotly_dark",
            height=400
        )
        
        return fig
    
    @staticmethod
    def trade_distribution(
        trades: pd.DataFrame,
        title: str = "Trade Distribution"
    ) -> go.Figure:
        """Generate trade distribution chart"""
        if not PLOTLY_AVAILABLE:
            raise ImportError("Plotly not installed")
        
        fig = make_subplots(
            rows=1, cols=2,
            subplot_titles=('Profit Distribution', 'Trade Types')
        )
        
        # Profit histogram
        fig.add_trace(
            go.Histogram(
                x=trades['profit'],
                nbinsx=30,
                name='Profit',
                marker_color='purple'
            ),
            row=1, col=1
        )
        
        # Trade types (winners vs losers)
        winners = len(trades[trades['profit'] > 0])
        losers = len(trades[trades['profit'] < 0])
        break_even = len(trades[trades['profit'] == 0])
        
        fig.add_trace(
            go.Pie(
                labels=['Winners', 'Losers', 'Break Even'],
                values=[winners, losers, break_even],
                name='Trade Types',
                marker_colors=['green', 'red', 'gray']
            ),
            row=1, col=2
        )
        
        fig.update_layout(
            title=title,
            template="plotly_dark",
            height=400
        )
        
        return fig
    
    @staticmethod
    def correlation_matrix(
        returns: pd.DataFrame,
        title: str = "Correlation Matrix"
    ) -> go.Figure:
        """Generate correlation heatmap"""
        if not PLOTLY_AVAILABLE:
            raise ImportError("Plotly not installed")
        
        corr = returns.corr()
        
        fig = go.Figure(
            data=go.Heatmap(
                z=corr.values,
                x=corr.columns,
                y=corr.index,
                colorscale='RdBu',
                zmin=-1,
                zmax=1,
                text=corr.round(2).values,
                texttemplate='%{text}',
                textfont={"size": 10}
            )
        )
        
        fig.update_layout(
            title=title,
            height=500,
            template="plotly_dark"
        )
        
        return fig