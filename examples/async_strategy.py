# examples/async_strategy.py
"""
Example async strategy using fluxV
"""
import asyncio
import logging
from datetime import datetime, timedelta

from fluxV import (
    create_broker,
    OrderRequest,
    OrderAction,
    OrderType,
    Timeframe,
    setup_logging
)

# Setup logging
setup_logging(level="INFO")


class MovingAverageCrossoverStrategy:
    """Simple moving average crossover strategy with async operations"""
    
    def __init__(self, broker, symbol: str = "EURUSD"):
        self.broker = broker
        self.symbol = symbol
        self.fast_ma = 10
        self.slow_ma = 30
        self.volume = 0.1
        self.running = True
    
    async def run(self):
        """Main strategy loop"""
        print(f"Starting strategy for {self.symbol}")
        
        # Get initial positions
        await self._check_and_close_positions()
        
        # Stream bars and process them
        async for bar in await self.broker.stream_rates(self.symbol, Timeframe.H1):
            if not self.running:
                break
            
            # Calculate moving averages
            bars = await self.broker.get_rates_latest(self.symbol, Timeframe.H1, self.slow_ma + 1)
            
            if len(bars) < self.slow_ma:
                continue
            
            closes = [b.close for b in bars]
            fast_ma = sum(closes[-self.fast_ma:]) / self.fast_ma
            slow_ma = sum(closes[-self.slow_ma:]) / self.slow_ma
            
            # Get current positions
            positions = await self.broker.get_positions(self.symbol)
            
            # Trading logic
            if fast_ma > slow_ma and not positions:
                # Buy signal
                await self._enter_long(bar)
                
            elif fast_ma < slow_ma and positions:
                # Sell signal
                await self._exit_long(positions)
    
    async def _enter_long(self, bar):
        """Enter long position"""
        print(f"BUY SIGNAL at {bar.time}: {bar.close}")
        
        request = OrderRequest(
            symbol=self.symbol,
            action=OrderAction.BUY,
            volume=self.volume,
            order_type=OrderType.MARKET,
            sl=bar.close * 0.99,
            tp=bar.close * 1.01,
            comment="MA Crossover Long"
        )
        
        result = await self.broker.place_order(request)
        print(f"Order placed: {result.order_id} - {result.status.value}")
        
        # Wait for order fill
        if result.status == OrderStatus.PENDING:
            filled = await self.broker.wait_for_order_fill(result.order_id)
            print(f"Order filled at {filled.price}")
    
    async def _exit_long(self, positions):
        """Exit long position"""
        print(f"SELL SIGNAL - Closing positions")
        
        for pos in positions:
            if pos.symbol == self.symbol:
                success = await self.broker.close_position(pos.ticket)
                if success:
                    print(f"Closed position {pos.ticket} at {pos.price_current} - Profit: {pos.profit:.2f}")
    
    async def _check_and_close_positions(self):
        """Check and close any existing positions"""
        positions = await self.broker.get_positions(self.symbol)
        if positions:
            print(f"Found {len(positions)} existing positions - closing them")
            await self.broker.close_all_positions(self.symbol)
    
    def stop(self):
        """Stop the strategy"""
        self.running = False


async def run_live_strategy():
    """Run strategy in live mode"""
    print("=== Live Strategy ===")
    
    # Create and connect broker
    broker = await create_broker(
        "live",
        login=12345,  # Replace with your login
        password="your_password",  # Replace with your password
        server="Demo"  # Replace with your server
    )
    
    try:
        await broker.connect()
        print("Connected to MT5")
        
        # Get account info
        account = await broker.get_account_info()
        print(f"Account Balance: {account.balance} {account.currency}")
        
        # Run strategy
        strategy = MovingAverageCrossoverStrategy(broker, "EURUSD")
        
        try:
            await strategy.run()
        except KeyboardInterrupt:
            print("\nStopping strategy...")
            strategy.stop()
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await broker.disconnect()
        print("Disconnected")


async def run_backtest_strategy():
    """Run strategy in backtest mode"""
    print("\n=== Backtest Strategy ===")
    
    # Create mock broker
    broker = await create_broker(
        "backtest",
        initial_balance=10000,
        commission=0.001
    )
    
    # Load sample data (in practice, load from CSV)
    import pandas as pd
    import numpy as np
    
    dates = pd.date_range(start="2024-01-01", end="2024-12-31", freq="H")
    base_price = 1.2000
    trend = np.linspace(0, 0.01, len(dates))
    noise = np.random.normal(0, 0.0005, len(dates))
    prices = base_price + trend + np.cumsum(noise)
    
    data = pd.DataFrame({
        'time': dates,
        'open': prices,
        'high': prices + 0.0005,
        'low': prices - 0.0005,
        'close': prices + np.random.normal(0, 0.0002, len(dates)),
        'volume': np.random.randint(100, 1000, len(dates))
    })
    
    broker.load_data("EURUSD", Timeframe.H1, data)
    print("Loaded backtest data")
    
    # Run strategy
    strategy = MovingAverageCrossoverStrategy(broker, "EURUSD")
    
    try:
        await strategy.run()
    except KeyboardInterrupt:
        print("\nStopping backtest...")
        strategy.stop()
    
    # Get results
    stats = broker.get_stats()
    print("\n=== Backtest Results ===")
    print(f"Initial Balance: ${stats['initial_balance']:.2f}")
    print(f"Final Balance: ${stats['final_balance']:.2f}")
    print(f"Total Profit: ${stats['total_profit']:.2f}")
    print(f"Total Trades: {stats['total_trades']}")
    print(f"Win Rate: {stats['win_rate']:.1f}%")
    print(f"Max Drawdown: {stats['max_drawdown']:.2f}%")
    
    # Get equity curve
    equity_curve = broker.get_equity_curve()
    if len(equity_curve) > 0:
        print(f"Equity curve points: {len(equity_curve)}")
        print(f"Final equity: ${equity_curve['equity'].iloc[-1]:.2f}")


async def main():
    """Main entry point"""
    # Run backtest by default
    await run_backtest_strategy()
    
    # Uncomment to run live strategy
    # await run_live_strategy()


if __name__ == "__main__":
    asyncio.run(main())