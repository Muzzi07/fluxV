from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List, Any
from enum import Enum

from fluxV.core.types import OrderAction, OrderType, OrderStatus, PositionSide


@dataclass
class OrderRequest:
    """Request object for placing orders"""
    symbol: str
    action: OrderAction
    volume: float
    order_type: OrderType = OrderType.MARKET
    price: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None
    comment: Optional[str] = None
    magic: Optional[int] = None
    deviation: int = 20
    expiration: Optional[datetime] = None
    request_id: Optional[str] = None
    
    def __post_init__(self):
        if self.volume <= 0:
            raise ValueError("Volume must be positive")
        if self.order_type != OrderType.MARKET and self.price is None:
            raise ValueError("Price required for pending orders")
        if self.sl and self.tp and self.sl == self.tp:
            raise ValueError("SL and TP cannot be equal")


@dataclass
class OrderResult:
    """Result object for order placement"""
    order_id: int
    symbol: str
    action: OrderAction
    volume: float
    price: float
    sl: Optional[float]
    tp: Optional[float]
    comment: Optional[str]
    status: OrderStatus
    magic: Optional[int] = None
    message: Optional[str] = None
    filled_volume: float = 0.0
    remaining_volume: float = 0.0
    created_time: datetime = field(default_factory=datetime.now)
    filled_time: Optional[datetime] = None


@dataclass
class Position:
    """Position object representing an open trade"""
    ticket: int
    symbol: str
    action: OrderAction
    volume: float
    price_open: float
    price_current: float
    sl: Optional[float]
    tp: Optional[float]
    profit: float
    comment: Optional[str]
    magic: Optional[int]
    open_time: datetime
    swap: float = 0.0
    commission: float = 0.0
    
    @property
    def side(self) -> PositionSide:
        return PositionSide.LONG if self.action == OrderAction.BUY else PositionSide.SHORT
    
    @property
    def pnl_points(self) -> float:
        if self.action == OrderAction.BUY:
            return self.price_current - self.price_open
        return self.price_open - self.price_current
    
    @property
    def pnl_percent(self) -> float:
        if self.price_open == 0:
            return 0
        return (self.pnl_points / self.price_open) * 100


@dataclass
class Bar:
    """OHLCV bar data"""
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    tick_volume: int = 0
    spread: int = 0
    real_volume: int = 0
    
    def to_dict(self) -> Dict:
        return {
            'time': self.time,
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'close': self.close,
            'volume': self.volume
        }
    
    @property
    def midpoint(self) -> float:
        return (self.high + self.low) / 2
    
    @property
    def range(self) -> float:
        return self.high - self.low
    
    @property
    def is_bullish(self) -> bool:
        return self.close > self.open
    
    @property
    def is_bearish(self) -> bool:
        return self.close < self.open


@dataclass
class Tick:
    """Tick data"""
    time: datetime
    bid: float
    ask: float
    last: float
    volume: int
    flags: int
    
    @property
    def spread(self) -> float:
        return self.ask - self.bid
    
    @property
    def midpoint(self) -> float:
        return (self.bid + self.ask) / 2


@dataclass
class AccountInfo:
    """Account information"""
    balance: float
    equity: float
    margin: float
    free_margin: float
    leverage: int
    currency: str
    profit: float
    margin_level: Optional[float] = None
    server: Optional[str] = None
    name: Optional[str] = None
    company: Optional[str] = None
    trade_allowed: bool = True
    
    @property
    def is_healthy(self) -> bool:
        return self.free_margin > 0 and (self.margin_level is None or self.margin_level > 100)


@dataclass
class SymbolInfo:
    """Symbol information"""
    name: str
    digits: int
    point: float
    min_volume: float
    max_volume: float
    volume_step: float
    trade_contract_size: float
    spread: int
    tick_size: float
    tick_value: float
    description: Optional[str] = None
    trade_mode: Optional[str] = None
    is_tradable: bool = True
    is_visible: bool = True
    path: Optional[str] = None
    
    def normalize_price(self, price: float) -> float:
        return round(price, self.digits)
    
    def normalize_volume(self, volume: float) -> float:
        step = self.volume_step
        return round(volume / step) * step


@dataclass
class MarketSnapshot:
    """Market snapshot at a point in time"""
    symbol: str
    timestamp: datetime
    bid: float
    ask: float
    last: float
    volume: int
    open_interest: int = 0
    
    @property
    def spread(self) -> float:
        return self.ask - self.bid
    
    @property
    def midpoint(self) -> float:
        return (self.bid + self.ask) / 2