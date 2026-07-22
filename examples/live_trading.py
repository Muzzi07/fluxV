import asyncio
import logging
import os
from datetime import datetime

from dotenv import load_dotenv

from fluxV import (
    create_broker,
    setup_logging,
    OrderRequest,
    OrderAction,
    OrderType,
    Timeframe,
    OrderStatus,
)
from fluxV.core.exceptions import (
    ConnectionError,
    MarketClosedError,
    InsufficientBalanceError,
)

# Try to load credentials from .env file
load_dotenv()

# Setup logging
setup_logging(level="INFO")
logger = logging.getLogger(__name__)


async def get_account_summary(broker):
    """Display account information."""
    try:
        account = await broker.get_account_info()
        print("\n" + "=" * 50)
        print("  Account Summary")
        print("=" * 50)
        print(f"  Name:           {account.name or 'N/A'}")
        print(f"  Server:         {account.server or 'N/A'}")
        print(f"  Balance:        ${account.balance:>10.2f}")
        print(f"  Equity:         ${account.equity:>10.2f}")
        print(f"  Free Margin:    ${account.free_margin:>10.2f}")
        print(f"  Margin Level:   {account.margin_level:>10.2f}%")
        print(f"  Leverage:       1:{account.leverage}")
        print(f"  Currency:       {account.currency}")
        print(f"  Profit:         ${account.profit:>10.2f}")
        print(f"  Health:         {'✅ Good' if account.is_healthy else '⚠️ Warning'}")
        print("=" * 50)
        return account
    except Exception as e:
        logger.error(f"Failed to get account info: {e}")
        return None


async def display_symbol_info(broker, symbol="EURUSD"):
    """Display symbol information."""
    try:
        info = await broker.get_symbol_info(symbol)
        if info:
            print(f"\n  Symbol Info - {symbol}")
            print(f"    Digits:      {info.digits}")
            print(f"    Point:       {info.point}")
            print(f"    Spread:      {info.spread}")
            print(f"    Min Volume:  {info.min_volume}")
            print(f"    Max Volume:  {info.max_volume}")
            print(f"    Tradable:    {info.is_tradable}")
            return info
        else:
            logger.warning(f"Symbol {symbol} not found")
            return None
    except Exception as e:
        logger.error(f"Failed to get symbol info: {e}")
        return None


async def get_market_snapshot(broker, symbol="EURUSD"):
    """Get current market snapshot."""
    try:
        snapshot = await broker.get_snapshot(symbol)
        print(f"\n  Market Snapshot - {symbol}")
        print(f"    Time:   {snapshot.timestamp}")
        print(f"    Bid:    {snapshot.bid:.5f}")
        print(f"    Ask:    {snapshot.ask:.5f}")
        print(f"    Spread: {snapshot.spread:.5f}")
        print(f"    Last:   {snapshot.last:.5f}")
        return snapshot
    except Exception as e:
        logger.error(f"Failed to get snapshot: {e}")
        return None


async def get_recent_bars(broker, symbol="EURUSD", timeframe=Timeframe.H1, count=5):
    """Display recent bars."""
    try:
        bars = await broker.get_rates_latest(symbol, timeframe, count)
        if bars:
            print(f"\n  Recent {count} Bars ({symbol}, {timeframe.name})")
            for bar in bars:
                direction = "↑" if bar.is_bullish else "↓"
                print(
                    f"    {bar.time.strftime('%Y-%m-%d %H:%M')} | "
                    f"O:{bar.open:.5f} H:{bar.high:.5f} "
                    f"L:{bar.low:.5f} C:{bar.close:.5f} "
                    f"V:{bar.volume} {direction}"
                )
        return bars
    except Exception as e:
        logger.error(f"Failed to get bars: {e}")
        return []


async def place_demo_order(broker, symbol="EURUSD"):
    """
    Place a demo market order to check if trading works.

    NOTE: This example only prints the order request for safety.
    Uncomment the actual placement when you're ready to trade.
    """
    print(f"\n  Demo Order Request:")
    print(f"    Symbol:  {symbol}")
    print(f"    Action:  BUY")
    print(f"    Volume:  0.01")
    print(f"    Type:    MARKET")
    print(f"    Status:  ⚠️  DRY RUN - No order placed")

    # Dry run - just print what would happen
    # Uncomment the following to actually place the order:
    #
    # request = OrderRequest(
    #     symbol=symbol,
    #     action=OrderAction.BUY,
    #     volume=0.01,
    #     order_type=OrderType.MARKET,
    #     sl=snapshot.bid * 0.995,
    #     tp=snapshot.bid * 1.005,
    #     comment="fluxV Demo Order",
    #     deviation=10,
    # )
    #
    # try:
    #     result = await broker.place_order(request)
    #     print(f"  ✅ Order placed: #{result.order_id} @ {result.price:.5f}")
    #
    #     if result.status == OrderStatus.PENDING:
    #         filled = await broker.wait_for_order_fill(result.order_id, timeout=10)
    #         print(f"  ✅ Order filled @ {filled.price:.5f}")
    #
    # except InsufficientBalanceError as e:
    #     logger.error(f"Insufficient balance: {e}")
    # except MarketClosedError as e:
    #     logger.error(f"Market closed: {e}")
    # except Exception as e:
    #     logger.error(f"Order failed: {e}")


async def show_open_positions(broker, symbol=None):
    """Display open positions."""
    try:
        positions = await broker.get_positions(symbol)
        if positions:
            print(f"\n  Open Positions ({len(positions)}):")
            for pos in positions:
                direction = "📈 LONG" if pos.side.value == "long" else "📉 SHORT"
                pnl_str = f"+${pos.profit:.2f}" if pos.profit >= 0 else f"-${abs(pos.profit):.2f}"
                print(
                    f"    #{pos.ticket} {pos.symbol} {direction} "
                    f"Vol:{pos.volume:.2f} "
                    f"Open:{pos.price_open:.5f} "
                    f"Current:{pos.price_current:.5f} "
                    f"PnL:{pnl_str}"
                )
        else:
            print(f"\n  No open positions.")
        return positions
    except Exception as e:
        logger.error(f"Failed to get positions: {e}")
        return []


async def run_live_demo():
    """Run a live trading demo (read-only + info)."""
    print("=" * 60)
    print("  fluxV Live Trading Demo")
    print("=" * 60)
    print("  This demo connects to MT5 and shows account information.")
    print("  No real orders are placed (dry run mode).")
    print("=" * 60)

    # Get credentials from environment or prompt
    login = os.getenv("MT5_LOGIN")
    password = os.getenv("MT5_PASSWORD")
    server = os.getenv("MT5_SERVER")

    # If not in env, use demo defaults (will likely fail without real credentials)
    if not all([login, password, server]):
        print("\n  ⚠️  No MT5 credentials found in environment.")
        print("     Set MT5_LOGIN, MT5_PASSWORD, and MT5_SERVER in a .env file")
        print("     or run with these environment variables set.\n")
        print("  Proceeding with assumed demo credentials...")
        login = login or 12345678
        password = password or "your_password"
        server = server or "ICMarkets-Demo"

    # Create broker
    logger.info("Creating live MT5 broker...")
    broker = create_broker(
        "live",
        login=int(login) if login else None,
        password=password,
        server=server,
    )

    try:
        # Connect to MT5
        logger.info("Connecting to MT5 (this may take a moment)...")
        connected = await broker.connect()
        if not connected:
            logger.error("Failed to connect to MT5. Is the terminal running?")
            return

        print("\n✅ Connected to MT5 terminal!")

        # Display account info
        account = await get_account_summary(broker)
        if not account:
            logger.error("Could not retrieve account information.")
            await broker.disconnect()
            return

        # Show symbol info
        await display_symbol_info(broker, "EURUSD")

        # Get market snapshot
        await get_market_snapshot(broker, "EURUSD")

        # Get recent bars
        await get_recent_bars(broker, "EURUSD", Timeframe.H1, 5)

        # Show open positions
        await show_open_positions(broker)

        # Show demo order (dry run)
        await place_demo_order(broker, "EURUSD")

        print("\n" + "=" * 60)
        print("  Demo complete! No real orders were executed.")
        print("  To trade live, update the place_demo_order() function.")
        print("=" * 60)

    except ConnectionError as e:
        logger.error(f"Connection error: {e}")
        print("\n  ❌ Could not connect to MT5. Make sure:")
        print("     - MetaTrader 5 is installed and running")
        print("     - The terminal path is correct")
        print("     - Login credentials are valid")
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
    finally:
        await broker.disconnect()
        print("\nDisconnected from MT5.")


async def main():
    """Main entry point."""
    await run_live_demo()


if __name__ == "__main__":
    asyncio.run(main())
