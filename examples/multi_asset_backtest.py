import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

from fluxV.backtest.engine import MultiAssetBacktestEngine
from fluxV.backtest.dashboard_backtest import BacktestDashboardIntegration
from fluxV.data.data_manager import DataManager
from fluxV.data.news import NewsManager
from fluxV.core.types import Timeframe, OrderAction
from fluxV.core.models import OrderRequest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MultiAssetStrategy:
    """Example strategy for multi-asset trading"""
    
    def __init__(self, symbols: List[str]):
        self.symbols = symbols
        self.ma_fast = 10
        self.ma_slow = 30
        self.volume = 0.1
        
        # Track moving averages for each symbol
        self.prices = {symbol: [] for symbol in symbols}
        self.positions = {}
        
    async def on_bar(
        self,
        symbol: str,
        bar,
        portfolio,
        all_bars: dict,
        news: list
    ):
        """Called on each bar for each symbol"""
        
        # Update price history
        self.prices[symbol].append(bar.close)
        if len(self.prices[symbol]) > self.ma_slow:
            self.prices[symbol] = self.prices[symbol][-self.ma_slow:]
        
        if len(self.prices[symbol]) < self.ma_slow:
            return
        
        # Calculate moving averages
        fast_ma = sum(self.prices[symbol][-self.ma_fast:]) / self.ma_fast
        slow_ma = sum(self.prices[symbol][-self.ma_slow:]) / self.ma_slow
        
        # Check current positions for this symbol
        current_positions = [
            p for p in portfolio.positions.get(symbol, [])
            if p.symbol == symbol
        ]
        
        # News sentiment override
        news_impact = self._analyze_news(news, symbol)
        
        # Trading logic with news sentiment
        if fast_ma > slow_ma and not current_positions and news_impact >= 0:
            # Buy signal with positive sentiment
            await self._open_position(
                portfolio, symbol, bar.close,
                OrderAction.BUY, "MA Crossover + Positive News"
            )
            
        elif fast_ma < slow_ma and current_positions and news_impact <= 0:
            # Sell signal with negative sentiment
            for pos in current_positions:
                await self._close_position(portfolio, symbol, pos.ticket, bar.close)
        
        # Pairs trading opportunity
        if len(self.symbols) >= 2:
            await self._check_pairs_trading(portfolio, all_bars)
    
    async def _open_position(
        self,
        portfolio,
        symbol: str,
        price: float,
        action: OrderAction,
        reason: str
    ):
        """Open a new position"""
        # Calculate position size based on portfolio equity
        volume = self.volume
        
        # Create position
        from fluxV.core.models import Position
        import time
        
        execution_price = price
        if action == OrderAction.BUY:
            execution_price = price + 0.0001
        else:
            execution_price = price - 0.0001
        
        position = Position(
            ticket=int(time.time() * 1000) + len(portfolio.positions.get(symbol, [])),
            symbol=symbol,
            action=action,
            volume=volume,
            price_open=execution_price,
            price_current=execution_price,
            sl=execution_price * 0.99 if action == OrderAction.BUY else execution_price * 1.01,
            tp=execution_price * 1.01 if action == OrderAction.BUY else execution_price * 0.99,
            profit=0,
            comment=reason,
            magic=12345,
            open_time=datetime.now(),
            commission=volume * 0.001
        )
        
        # Deduct margin and commission
        margin_required = execution_price * volume * 0.01
        portfolio.cash -= margin_required + position.commission
        portfolio.add_position(symbol, position)
        
        logger.info(f"Opened {action.value} position for {symbol}: ${execution_price:.5f} - {reason}")
    
    async def _close_position(self, portfolio, symbol: str, ticket: int, price: float):
        """Close a position"""
        positions = portfolio.positions.get(symbol, [])
        position = next((p for p in positions if p.ticket == ticket), None)
        
        if not position:
            return
        
        if position.action == OrderAction.BUY:
            profit = (price - position.price_open) * position.volume
        else:
            profit = (position.price_open - price) * position.volume
        
        # Add back margin
        margin_required = position.price_open * position.volume * 0.01
        portfolio.cash += margin_required + profit
        
        portfolio.remove_position(symbol, ticket)
        
        logger.info(f"Closed position for {symbol}: ${price:.5f} - Profit: ${profit:.2f}")
    
    async def _check_pairs_trading(self, portfolio, all_bars: dict):
        """Check for pairs trading opportunities"""
        if len(self.symbols) < 2:
            return
        
        # Calculate spread between two symbols
        symbol1 = self.symbols[0]
        symbol2 = self.symbols[1]
        
        if symbol1 not in all_bars or symbol2 not in all_bars:
            return
        
        bar1 = all_bars[symbol1]
        bar2 = all_bars[symbol2]
        
        # Normalize prices
        price1 = bar1.close / 100 if 'JPY' in symbol1 else bar1.close
        price2 = bar2.close / 100 if 'JPY' in symbol2 else bar2.close
        
        spread = price1 - price2
        
        # Simple threshold-based trading
        if spread > 0.01:
            # Short spread (sell symbol1, buy symbol2)
            positions1 = [p for p in portfolio.positions.get(symbol1, []) if p.symbol == symbol1]
            if not positions1:
                await self._open_position(portfolio, symbol1, bar1.close, OrderAction.SELL, "Pairs Trading - Short")
            
            positions2 = [p for p in portfolio.positions.get(symbol2, []) if p.symbol == symbol2]
            if not positions2:
                await self._open_position(portfolio, symbol2, bar2.close, OrderAction.BUY, "Pairs Trading - Long")
                
        elif spread < -0.01:
            # Long spread (buy symbol1, sell symbol2)
            positions1 = [p for p in portfolio.positions.get(symbol1, []) if p.symbol == symbol1]
            if not positions1:
                await self._open_position(portfolio, symbol1, bar1.close, OrderAction.BUY, "Pairs Trading - Long")
            
            positions2 = [p for p in portfolio.positions.get(symbol2, []) if p.symbol == symbol2]
            if not positions2:
                await self._open_position(portfolio, symbol2, bar2.close, OrderAction.SELL, "Pairs Trading - Short")
    
    def _analyze_news(self, news: list, symbol: str) -> int:
        """Analyze news sentiment for a symbol"""
        if not news:
            return 0
        
        sentiment_score = 0
        for event in news:
            if event.currency in symbol:
                if event.sentiment.value == "positive":
                    sentiment_score += 1
                elif event.sentiment.value == "negative":
                    sentiment_score -= 1
        
        return sentiment_score


async def run_multi_asset_backtest():
    """Run multi-asset backtest with dashboard"""
    
    # Define symbols for multi-asset trading
    symbols = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]
    
    # Create data manager
    data_manager = DataManager()
    
    # Create backtest engine
    engine = MultiAssetBacktestEngine(
        initial_capital=100000,
        commission=0.001,
        slippage=0.0001,
        data_manager=data_manager
    )
    
    # Create strategy
    strategy = MultiAssetStrategy(symbols)
    
    # Define time range
    from_date = datetime(2024, 1, 1)
    to_date = datetime(2024, 12, 31)
    
    # Run backtest
    print("Starting multi-asset backtest with dashboard...")
    print(f"Trading symbols: {symbols}")
    print(f"Period: {from_date.date()} to {to_date.date()}")
    
    report = await engine.run(
        symbols=symbols,
        timeframe=Timeframe.H4,
        from_date=from_date,
        to_date=to_date,
        strategy_callback=strategy.on_bar,
        show_dashboard=True,
        dashboard_interval=1.0,
        use_news=True
    )
    
    # Print results
    print("\n" + "="*60)
    print("BACKTEST RESULTS")
    print("="*60)
    
    print(f"\nPortfolio Performance:")
    print(f"  Initial Capital: ${report.get('initial_capital', 0):,.2f}")
    print(f"  Final Equity: ${report.get('final_equity', 0):,.2f}")
    print(f"  Total Return: {report.get('total_return_pct', 0):.2f}%")
    print(f"  Sharpe Ratio: {report.get('sharpe_ratio', 0):.2f}")
    print(f"  Max Drawdown: {report.get('max_drawdown', 0):.2f}%")
    print(f"  Total Trades: {report.get('total_trades', 0)}")
    print(f"  Win Rate: {report.get('win_rate', 0):.1f}%")
    print(f"  Profit Factor: {report.get('profit_factor', 0):.2f}")
    
    print("\nSymbol Performance:")
    for symbol, perf in report.get('symbol_performance', {}).items():
        print(f"  {symbol}:")
        print(f"    Trades: {perf['total_trades']}")
        print(f"    P&L: ${perf['profit']:,.2f}")
        print(f"    Win Rate: {perf['win_rate']:.1f}%")
    
    print("\n" + "="*60)
    
    # Save dashboard
    if engine.dashboard:
        engine.dashboard.save_html("multi_asset_backtest_dashboard.html")
        print("\nDashboard saved to multi_asset_backtest_dashboard.html")


if __name__ == "__main__":
    asyncio.run(run_multi_asset_backtest())