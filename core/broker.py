"""
Abstract async broker interface for fluxV

Defines the complete set of operations that both MT5Broker (live)
and MockBroker (backtest) must implement.
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, AsyncIterator, Callable, Awaitable
from datetime import datetime

from fluxV.core.types import (
    OrderRequest,
    OrderResult,
    Position,
    Bar,
    Tick,
    AccountInfo,
    SymbolInfo,
    Timeframe,
    MarketSnapshot,
)


class Broker(ABC):
    """
    Abstract async broker interface that both MT5Broker and MockBroker implement.

    All methods are async for non-blocking operations.
    Provides a unified API so the same code works for both backtesting and live trading.
    """
    
    # -------------------------------------------------------------------------
    # Connection Management
    # -------------------------------------------------------------------------

    @abstractmethod
    async def connect(self, **kwargs) -> bool:
        """Connect to the broker/trading terminal"""
        pass
    
    @abstractmethod
    async def disconnect(self) -> bool:
        """Disconnect from the broker/trading terminal"""
        pass
    
    @abstractmethod
    async def is_connected(self) -> bool:
        """Check if connected to the broker"""
        pass
    
    @abstractmethod
    def get_mode(self) -> str:
        """Return the current mode: 'live' or 'backtest'"""
        pass

    # -------------------------------------------------------------------------
    # Account Information
    # -------------------------------------------------------------------------

    @abstractmethod
    async def get_account_info(self) -> AccountInfo:
        """Get current account information (balance, equity, margin, etc.)"""
        pass
    
    @abstractmethod
    async def get_symbol_info(self, symbol: str) -> Optional[SymbolInfo]:
        """Get symbol information (digits, spread, min/max volume, etc.)"""
        pass
    
    async def get_symbols(self) -> List[str]:
        """Get list of all available symbols from the terminal"""
        return []

    async def subscribe_symbols(self, symbols: List[str]) -> bool:
        """Subscribe to symbols in Market Watch for real-time data"""
        return True

    async def unsubscribe_symbols(self, symbols: List[str]) -> bool:
        """Unsubscribe symbols from Market Watch"""
        return True

    # -------------------------------------------------------------------------
    # Market Data - Bars / OHLCV
    # -------------------------------------------------------------------------

    @abstractmethod
    async def get_rates(
        self,
        symbol: str,
        timeframe: Timeframe,
        from_date: datetime,
        to_date: datetime,
    ) -> List[Bar]:
        """Get historical OHLCV bars for a symbol within a date range"""
        pass
    
    @abstractmethod
    async def get_rates_latest(
        self, symbol: str, timeframe: Timeframe, count: int
    ) -> List[Bar]:
        """Get the most recent n OHLCV bars for a symbol"""
        pass
    
    # -------------------------------------------------------------------------
    # Market Data - Ticks
    # -------------------------------------------------------------------------

    async def get_ticks(
        self,
        symbol: str,
        from_date: datetime,
        to_date: datetime,
        flags: int = 0,
    ) -> List[Tick]:
        """Get historical ticks for a symbol within a date range.

        Args:
            symbol: Symbol name (e.g. 'EURUSD')
            from_date: Start datetime
            to_date: End datetime
            flags: COPY_TICKS_ALL, COPY_TICKS_INFO, or COPY_TICKS_TRADE
        """
        raise NotImplementedError("get_ticks not implemented by this broker")

    async def get_ticks_latest(
        self, symbol: str, count: int, flags: int = 0
    ) -> List[Tick]:
        """Get the most recent n ticks for a symbol.

        Args:
            symbol: Symbol name
            count: Number of ticks to retrieve
            flags: COPY_TICKS_ALL, COPY_TICKS_INFO, or COPY_TICKS_TRADE
        """
        raise NotImplementedError("get_ticks_latest not implemented by this broker")

    @abstractmethod
    async def get_snapshot(self, symbol: str) -> MarketSnapshot:
        """Get current market snapshot (latest bid/ask/last) for a symbol"""
        pass

    # -------------------------------------------------------------------------
    # Streaming
    # -------------------------------------------------------------------------

    @abstractmethod
    async def stream_rates(
        self,
        symbol: str,
        timeframe: Timeframe,
        callback: Optional[Callable[[Bar], Awaitable[None]]] = None,
    ) -> AsyncIterator[Bar]:
        """
        Stream real-time bars for a symbol.
        If callback is provided, calls it for each bar instead of yielding.
        """
        pass
    
    @abstractmethod
    async def stream_ticks(
        self,
        symbol: str,
        callback: Optional[Callable[[Tick], Awaitable[None]]] = None,
    ) -> AsyncIterator[Tick]:
        """
        Stream real-time ticks for a symbol.
        If callback is provided, calls it for each tick instead of yielding.
        """
        pass
    
    # -------------------------------------------------------------------------
    # Order Placement & Management
    # -------------------------------------------------------------------------

    @abstractmethod
    async def place_order(self, request: OrderRequest) -> OrderResult:
        """Place an order with the broker (market, limit, or stop)"""
        pass
    
    @abstractmethod
    async def wait_for_order_fill(
        self, order_id: int, timeout: float = 30.0
    ) -> OrderResult:
        """Wait for a pending order to be filled asynchronously"""
        pass
    
    # -------------------------------------------------------------------------
    # Position Management
    # -------------------------------------------------------------------------

    @abstractmethod
    async def get_positions(
        self, symbol: Optional[str] = None
    ) -> List[Position]:
        """Get all open positions, optionally filtered by symbol"""
        pass

    @abstractmethod
    async def close_position(self, ticket: int) -> bool:
        """Close a position by ticket number"""
        pass
    
    @abstractmethod
    async def close_all_positions(
        self, symbol: Optional[str] = None
    ) -> bool:
        """Close all positions, optionally filtered by symbol"""
        pass
    
    @abstractmethod
    async def modify_position(
        self,
        ticket: int,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        trailing_stop: Optional[float] = None,
    ) -> bool:
        """Modify stop loss and take profit for an open position"""
        pass
    
    async def partial_close_position(
        self, ticket: int, volume: float
    ) -> bool:
        """Partially close a position by specifying volume to close"""
        raise NotImplementedError(
            "partial_close_position not implemented by this broker"
        )

    # -------------------------------------------------------------------------
    # Pending Orders
    # -------------------------------------------------------------------------

    @abstractmethod
    async def get_pending_orders(
        self, symbol: Optional[str] = None
    ) -> List[OrderResult]:
        """Get all pending orders, optionally filtered by symbol"""
        pass
    
    @abstractmethod
    async def cancel_order(self, ticket: int) -> bool:
        """Cancel a pending order by ticket number"""
        pass
    
    @abstractmethod
    async def cancel_all_orders(
        self, symbol: Optional[str] = None
    ) -> bool:
        """Cancel all pending orders, optionally filtered by symbol"""
        pass

    async def modify_order(
        self,
        ticket: int,
        price: Optional[float] = None,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        expiration: Optional[datetime] = None,
    ) -> bool:
        """Modify a pending order's parameters"""
        raise NotImplementedError(
            "modify_order not implemented by this broker"
        )

    # -------------------------------------------------------------------------
    # Trade History
    # -------------------------------------------------------------------------

    async def get_history_deals(
        self,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        symbol: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get historical deals (filled orders)"""
        raise NotImplementedError(
            "get_history_deals not implemented by this broker"
        )

    async def get_history_orders(
        self,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        symbol: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get historical orders (including cancelled/pending)"""
        raise NotImplementedError(
            "get_history_orders not implemented by this broker"
        )

    # -------------------------------------------------------------------------
    # Health & Utility
    # -------------------------------------------------------------------------

    async def health_check(self) -> bool:
        """Check if broker is healthy and operational"""
        try:
            info = await self.get_account_info()
            return info.is_healthy
        except Exception:
            return False

    async def ping(self) -> bool:
        """Ping the broker to check connectivity"""
        return await self.is_connected()

    async def get_terminal_info(self) -> Dict[str, Any]:
        """Get information about the trading terminal (MT5 version, etc.)"""
        return {}

    async def get_last_error(self) -> Optional[str]:
        """Get the last error message from the broker"""
        return None
