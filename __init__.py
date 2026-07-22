# fluxV/__init__.py
"""
fluxV — Async-First Python Library for MetaTrader 5 Algorithmic Trading
"""

__version__ = "0.3.0"

# ── Core types ──────────────────────────────────────────────────────────────
from fluxV.core.broker import Broker
from fluxV.core.models import (
    OrderRequest,
    OrderResult,
    Position,
    Bar,
    Tick,
    AccountInfo,
    SymbolInfo,
    MarketSnapshot,
)
from fluxV.core.types import (
    OrderAction,
    OrderType,
    Timeframe,
    OrderStatus,
    PositionSide,
)
from fluxV.core.exceptions import (
    fluxVError,
    ConnectionError as fluxVConnectionError,
    OrderError,
    DataError,
    SymbolNotFoundError,
    InsufficientBalanceError,
    InvalidOrderError,
    MarketClosedError,
    TimeoutError as fluxVTimeoutError,
    SlippageError,
)

# ── Broker implementations ─────────────────────────────────────────────────
# MT5Broker is lazy-loaded to avoid requiring MetaTrader5 on macOS/Linux.
_MT5_BROKER_CLASS = None

def _get_mt5_broker_class():
    global _MT5_BROKER_CLASS
    if _MT5_BROKER_CLASS is None:
        from fluxV.live.mt5 import MT5Broker
        _MT5_BROKER_CLASS = MT5Broker
    return _MT5_BROKER_CLASS

from fluxV.backtest.mock import MockBroker

# ── Strategy base ───────────────────────────────────────────────────────────
from fluxV.strategies.base import BaseStrategy

# ── Utilities ───────────────────────────────────────────────────────────────
from fluxV.utils.logging import setup_logging, AsyncLogger
from fluxV.utils.rate_limiter import RateLimiter
from fluxV.utils.retry import async_retry

# ── Performance analysis ────────────────────────────────────────────────────
from fluxV.backtest.performance import PerformanceAnalyzer


async def create_broker(mode: str = "live", **kwargs):
    """Factory: create 'live' (MT5) or 'backtest' (Mock) broker."""
    if mode == "live":
        cls = _get_mt5_broker_class()
        return cls(**kwargs)
    elif mode == "backtest":
        return MockBroker(**kwargs)
    else:
        raise ValueError(f"Invalid mode: {mode}. Use 'live' or 'backtest'")


# Re-exports for backwards compat
ConnectionError = fluxVConnectionError
TimeoutError = fluxVTimeoutError


class MT5BrokerAccessor:
    """Property-like descriptor for lazy MT5Broker access."""
    def __get__(self, obj, objtype=None):
        return _get_mt5_broker_class()

MT5Broker = MT5BrokerAccessor()


__all__ = [
    "create_broker",
    "MT5Broker",
    "MockBroker",
    "Broker",
    "OrderRequest",
    "OrderResult",
    "Position",
    "Bar",
    "Tick",
    "AccountInfo",
    "SymbolInfo",
    "MarketSnapshot",
    "OrderAction",
    "OrderType",
    "Timeframe",
    "OrderStatus",
    "PositionSide",
    "fluxVError",
    "ConnectionError",
    "OrderError",
    "DataError",
    "SymbolNotFoundError",
    "InsufficientBalanceError",
    "InvalidOrderError",
    "MarketClosedError",
    "TimeoutError",
    "SlippageError",
    "BaseStrategy",
    "setup_logging",
    "AsyncLogger",
    "RateLimiter",
    "async_retry",
    "PerformanceAnalyzer",
]