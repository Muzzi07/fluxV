"""
Report generator for backtest results

Generates comprehensive HTML reports with charts and statistics.
"""
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


class ReportGenerator:
    """Generate backtest reports in various formats"""

    @staticmethod
    def generate_html_report(
        stats: Dict,
        equity_curve: pd.DataFrame,
        trades: pd.DataFrame,
        output_file: str = "backtest_report.html",
        title: str = "Backtest Report"
    ) -> str:
        """
        Generate comprehensive HTML report from backtest results.

        Args:
            stats: Performance statistics dict
            equity_curve: DataFrame with equity curve data
            trades: DataFrame with trade history
            output_file: Path to save the HTML file
            title: Report title

        Returns:
            Path to generated HTML file
        """
        # Generate chart HTML
        charts_html = ""
        if PLOTLY_AVAILABLE:
            charts_html = ReportGenerator._generate_charts_html(
                equity_curve, trades, stats
            )

        # Build stats table
        stats_rows = ""
        stat_items = [
            ("Initial Balance", f"${stats.get('initial_balance', 0):,.2f}"),
            ("Final Balance", f"${stats.get('final_balance', 0):,.2f}"),
            ("Total Profit", f"${stats.get('total_profit', 0):,.2f}"),
            ("Total Trades", str(stats.get('total_trades', 0))),
            ("Winning Trades", str(stats.get('winning_trades', 0))),
            ("Losing Trades", str(stats.get('losing_trades', 0))),
            ("Win Rate", f"{stats.get('win_rate', 0):.1f}%"),
            ("Max Drawdown", f"{stats.get('max_drawdown', 0):.2f}%"),
            ("Profit Factor", f"{stats.get('profit_factor', 0):.2f}"),
            ("Sharpe Ratio", f"{stats.get('sharpe_ratio', 0):.2f}"),
            ("Total Commission", f"${stats.get('total_commission', 0):,.2f}"),
        ]

        for label, value in stat_items:
            stats_rows += f"""
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd;">{label}</td>
                <td style="padding: 8px; border: 1px solid #ddd; text-align: right; font-weight: bold;">{value}</td>
            </tr>
            """

        # Build trade table
        trades_rows = ""
        if len(trades) > 0:
            for _, trade in trades.head(50).iterrows():
                profit = trade.get('profit', 0)
                profit_class = "positive" if profit >= 0 else "negative"
                profit_str = f"+${profit:.2f}" if profit >= 0 else f"-${abs(profit):.2f}"

                trades_rows += f"""
                <tr>
                    <td style="padding: 6px; border: 1px solid #ddd;">{trade.get('ticket', '')}</td>
                    <td style="padding: 6px; border: 1px solid #ddd;">{trade.get('symbol', '')}</td>
                    <td style="padding: 6px; border: 1px solid #ddd;">{trade.get('action', '')}</td>
                    <td style="padding: 6px; border: 1px solid #ddd; text-align: right;">{trade.get('volume', 0):.2f}</td>
                    <td style="padding: 6px; border: 1px solid #ddd; text-align: right;">{trade.get('price_open', 0):.5f}</td>
                    <td style="padding: 6px; border: 1px solid #ddd; text-align: right;">{trade.get('price_close', 0):.5f}</td>
                    <td style="padding: 6px; border: 1px solid #ddd; text-align: right;" class="{profit_class}">{profit_str}</td>
                    <td style="padding: 6px; border: 1px solid #ddd;">{trade.get('close_reason', '')}</td>
                </tr>
                """

        # Compile HTML
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #1a1a2e;
            color: #eee;
        }}
        h1 {{ color: #e94560; border-bottom: 2px solid #e94560; padding-bottom: 10px; }}
        h2 {{ color: #0f3460; margin-top: 30px; }}
        table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
        th {{ background: #0f3460; color: white; padding: 10px; text-align: left; }}
        td {{ padding: 8px; border: 1px solid #333; }}
        tr:hover {{ background: #16213e; }}
        .stats-table {{ width: auto; min-width: 400px; }}
        .stats-table td {{ padding: 10px 15px; }}
        .positive {{ color: #4caf50; }}
        .negative {{ color: #f44336; }}
        .summary {{ 
            background: #16213e;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
            border: 1px solid #0f3460;
        }}
        .chart-container {{ margin: 20px 0; }}
        .footer {{ margin-top: 40px; text-align: center; color: #666; font-size: 12px; }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    <p style="color: #888;">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>

    <div class="summary">
        <h2>Performance Summary</h2>
        <table class="stats-table">
            {stats_rows}
        </table>
    </div>

    <div class="chart-container">
        <h2>Charts</h2>
        {charts_html}
    </div>

    <h2>Trade History (first 50 trades)</h2>
    <table>
        <thead>
            <tr>
                <th>Ticket</th>
                <th>Symbol</th>
                <th>Action</th>
                <th>Volume</th>
                <th>Open Price</th>
                <th>Close Price</th>
                <th>Profit</th>
                <th>Close Reason</th>
            </tr>
        </thead>
        <tbody>
            {trades_rows}
        </tbody>
    </table>
    {f'<p style="color: #888;">Showing first 50 trades of {len(trades)}</p>' if len(trades) > 50 else ''}

    <div class="footer">
        Generated by fluxV &copy; {datetime.now().year}
    </div>
</body>
</html>"""

        # Write to file
        with open(output_file, 'w') as f:
            f.write(html)

        logger.info(f"Report saved to {output_file}")
        return output_file

    @staticmethod
    def _generate_charts_html(
        equity_curve: pd.DataFrame,
        trades: pd.DataFrame,
        stats: Dict
    ) -> str:
        """Generate Plotly charts as HTML."""
        if not PLOTLY_AVAILABLE:
            return "<p>Install plotly (pip install plotly) for interactive charts.</p>"

        charts = []

        # 1. Equity curve
        if len(equity_curve) > 0 and 'time' in equity_curve.columns and 'equity' in equity_curve.columns:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=equity_curve['time'],
                y=equity_curve['equity'],
                name='Equity',
                line=dict(color='blue', width=2),
                fill='tozeroy',
                fillcolor='rgba(0,0,255,0.1)'
            ))
            fig.update_layout(
                title="Equity Curve",
                template="plotly_dark",
                height=400,
                margin=dict(l=50, r=50, t=50, b=50)
            )
            charts.append(pio.to_html(fig, full_html=False))

        # 2. Drawdown chart
        if len(equity_curve) > 1:
            peak = equity_curve['equity'].expanding().max()
            drawdown = (peak - equity_curve['equity']) / peak * 100

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=equity_curve['time'],
                y=drawdown,
                name='Drawdown',
                fill='tozeroy',
                line=dict(color='red', width=1),
                fillcolor='rgba(255,0,0,0.2)'
            ))
            fig.update_layout(
                title="Drawdown %",
                template="plotly_dark",
                height=300,
                margin=dict(l=50, r=50, t=50, b=50)
            )
            charts.append(pio.to_html(fig, full_html=False))

        # 3. Trade profit distribution
        if len(trades) > 0 and 'profit' in trades.columns:
            fig = go.Figure()
            fig.add_trace(go.Histogram(
                x=trades['profit'],
                nbinsx=20,
                name='Trade P&L',
                marker_color='purple',
                opacity=0.7
            ))
            fig.update_layout(
                title="Trade Profit Distribution",
                template="plotly_dark",
                height=300,
                margin=dict(l=50, r=50, t=50, b=50)
            )
            charts.append(pio.to_html(fig, full_html=False))

        return ''.join(
            f'<div class="chart-container">{chart}</div>'
            for chart in charts
        )

    @staticmethod
    def generate_json_report(
        stats: Dict,
        equity_curve: pd.DataFrame,
        trades: pd.DataFrame,
        output_file: str = "backtest_report.json"
    ) -> str:
        """Generate JSON report from backtest results."""
        report = {
            'generated_at': datetime.now().isoformat(),
            'statistics': stats,
            'trade_summary': {
                'total_trades': len(trades),
                'winning_trades': len(trades[trades['profit'] > 0]) if len(trades) > 0 else 0,
                'losing_trades': len(trades[trades['profit'] < 0]) if len(trades) > 0 else 0,
            },
            'equity_curve_summary': {
                'points': len(equity_curve),
                'final_equity': float(equity_curve['equity'].iloc[-1]) if len(equity_curve) > 0 else 0,
            }
        }

        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)

        logger.info(f"JSON report saved to {output_file}")
        return output_file


# Convenience function
def generate_report(
    stats: Dict,
    equity_curve: pd.DataFrame,
    trades: pd.DataFrame,
    output_dir: str = ".",
    prefix: str = "backtest"
) -> List[str]:
    """
    Generate both HTML and JSON reports.

    Args:
        stats: Performance statistics
        equity_curve: Equity curve DataFrame
        trades: Trade history DataFrame
        output_dir: Directory to save reports
        prefix: File name prefix

    Returns:
        List of generated file paths
    """
    os.makedirs(output_dir, exist_ok=True)

    files = []

    html_file = ReportGenerator.generate_html_report(
        stats, equity_curve, trades,
        output_file=os.path.join(output_dir, f"{prefix}_report.html")
    )
    files.append(html_file)

    json_file = ReportGenerator.generate_json_report(
        stats, equity_curve, trades,
        output_file=os.path.join(output_dir, f"{prefix}_report.json")
    )
    files.append(json_file)

    return files