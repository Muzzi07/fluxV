import os
from typing import Dict, List, Optional, Any
from datetime import datetime
import pandas as pd
import json

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    import plotly.io as pio
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False


class HTMLReport:
    """Generate HTML reports from backtest results"""
    
    @staticmethod
    def generate(
        stats: Dict,
        equity_curve: pd.DataFrame,
        trades: pd.DataFrame,
        output_file: str = "backtest_report.html",
        title: str = "Backtest Report"
    ):
        """Generate comprehensive HTML report"""
        
        # Generate charts
        charts = HTMLReport._generate_charts(equity_curve, trades, stats)
        
        # Create HTML
        html = HTMLReport._create_html_template(
            title=title,
            stats=stats,
            charts=charts,
            trades=trades
        )
        
        # Write to file
        with open(output_file, 'w') as f:
            f.write(html)
        
        return output_file
    
    @staticmethod
    def _generate_charts(
        equity_curve: pd.DataFrame,
        trades: pd.DataFrame,
        stats: Dict
    ) -> Dict:
        """Generate chart HTML strings"""
        if not PLOTLY_AVAILABLE:
            return {}
        
        charts = {}
        
        # Equity curve
        fig1 = go.Figure()
        fig1.add_trace(go.Scatter(
            x=equity_curve['time'],
            y=equity_curve['equity'],
            name='Equity',
            line=dict(color='blue', width=2)
        ))
        fig1.update_layout(
            title="Equity Curve",
            template="plotly_dark",
            height=400
        )
        charts['equity'] = pio.to_html(fig1, full_html=False)
        
        # Drawdown
        if len(equity_curve) > 1:
            peak = equity_curve['equity'].expanding().max()
            drawdown = (peak - equity_curve['equity']) / peak * 100
            
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(
                x=equity_curve['time'],
                y=drawdown,
                name='Drawdown',
                fill='tozeroy',
                line=dict(color='red', width=1)
            ))
            fig2.update_layout(
                title="Drawdown %",
                template="plotly_dark",
                height=300
            )
            charts['drawdown'] = pio.to_html(fig2, full_html=False)
        
        # Trade distribution
        if len(trades) > 0:
            fig3 = go.Figure()
            fig3.add_trace(go.Histogram(
                x=trades['profit'],
                nbinsx=20,
                name='Trade Profits',
                marker_color='purple'
            ))
            fig3.update_layout(
                title="Trade Profit Distribution",
                template="plotly_dark",
                height=300
            )
            charts['trades'] = pio.to_html(fig3, full_html=False)
        
        return charts
    
    @staticmethod
    def _create_html_template(
        title: str,
        stats: Dict,
        charts: Dict,
        trades: pd.DataFrame
    ) -> str:
        """Create HTML template"""
        
        # Format stats
        stats_html = f"""
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">${stats.get('final_balance', 0):,.2f}</div>
                <div class="stat-label">Final Balance</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${stats.get('total_profit', 0):,.2f}</div>
                <div class="stat-label">Total Profit</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats.get('total_trades', 0)}</div>
                <div class="stat-label">Total Trades</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats.get('win_rate', 0):.1f}%</div>
                <div class="stat-label">Win Rate</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats.get('sharpe_ratio', 0):.2f}</div>
                <div class="stat-label">Sharpe Ratio</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats.get('max_drawdown', 0):.2f}%</div>
                <div class="stat-label">Max Drawdown</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats.get('profit_factor', 0):.2f}</div>
                <div class="stat-label">Profit Factor</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats.get('avg_trade', 0):.2f}</div>
                <div class="stat-label">Avg Trade</div>
            </div>
        </div>
        """
        
        # Create tables
        trades_html = ""
        if len(trades) > 0:
            trades_html = trades.head(20).to_html(
                classes='trade-table',
                index=False
            )
        
        # Full HTML
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>{title}</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    background-color: #1a1a2e;
                    color: #eee;
                    margin: 0;
                    padding: 20px;
                }}
                .container {{
                    max-width: 1400px;
                    margin: 0 auto;
                }}
                h1 {{
                    color: #e94560;
                    border-bottom: 2px solid #e94560;
                    padding-bottom: 10px;
                }}
                .stats-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                    gap: 15px;
                    margin: 20px 0;
                }}
                .stat-card {{
                    background: #16213e;
                    padding: 15px;
                    border-radius: 8px;
                    text-align: center;
                    border: 1px solid #0f3460;
                }}
                .stat-value {{
                    font-size: 24px;
                    font-weight: bold;
                    color: #e94560;
                }}
                .stat-label {{
                    font-size: 12px;
                    color: #aaa;
                    margin-top: 5px;
                }}
                .chart-container {{
                    background: #16213e;
                    padding: 20px;
                    border-radius: 8px;
                    margin: 20px 0;
                    border: 1px solid #0f3460;
                }}
                .trade-table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin: 20px 0;
                    font-size: 12px;
                }}
                .trade-table th {{
                    background: #0f3460;
                    padding: 10px;
                    text-align: left;
                }}
                .trade-table td {{
                    padding: 8px;
                    border-bottom: 1px solid #0f3460;
                }}
                .trade-table tr:hover {{
                    background: #1a1a3e;
                }}
                .positive {{
                    color: #4caf50;
                }}
                .negative {{
                    color: #f44336;
                }}
                .footer {{
                    margin-top: 40px;
                    text-align: center;
                    color: #666;
                    font-size: 12px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>{title}</h1>
                <div style="color: #888; margin-bottom: 20px;">
                    Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                </div>
                
                <h2>Performance Summary</h2>
                {stats_html}
                
                <h2>Equity Curve</h2>
                <div class="chart-container">
                    {charts.get('equity', '')}
                </div>
                
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                    <div>
                        <h3>Drawdown</h3>
                        <div class="chart-container">
                            {charts.get('drawdown', '')}
                        </div>
                    </div>
                    <div>
                        <h3>Trade Distribution</h3>
                        <div class="chart-container">
                            {charts.get('trades', '')}
                        </div>
                    </div>
                </div>
                
                <h2>Trade History</h2>
                <div style="overflow-x: auto;">
                    {trades_html}
                </div>
                {f'<p style="color: #888;">Showing first 20 trades of {len(trades)}</p>' if len(trades) > 20 else ''}
                
                <div class="footer">
                    Generated by fluxV - {datetime.now().year}
                </div>
            </div>
        </body>
        </html>
        """
        
        return html