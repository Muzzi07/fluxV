"""
Type definitions and enums for fluxV
"""
from enum import Enum
from typing import Optional, Dict, Any, Union
from datetime import datetime
from dataclasses import dataclass, field


class OrderType(Enum):
    """Order types supported by fluxV"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class OrderAction(Enum):
    """Buy or Sell"""
    BUY = "BUY"
    SELL = "SELL"


class Timeframe(Enum):
    """MT5 timeframe constants"""
    M1 = 1
    M5 = 5
    M15 = 15
    M30 = 30
    H1 = 60
    H4 = 240
    D1 = 1440
    W1 = 10080
    MN1 = 43200
    
    @classmethod
    def from_string(cls, value: str):
        """Convert string to Timeframe enum"""
        mapping = {
            'M1': cls.M1, 'M5': cls.M5, 'M15': cls.M15, 'M30': cls.M30,
            'H1': cls.H1, 'H4': cls.H4, 'D1': cls.D1, 'W1': cls.W1, 'MN1': cls.MN1
        }
        return mapping.get(value.upper())


class OrderStatus(Enum):
    """Order status"""
    PENDING = "pending"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class PositionSide(Enum):
    """Position side"""
    LONG = "long"
    SHORT = "short"


class OrderExecution(Enum):
    """Order execution type"""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"


@dataclass
class Order:
    """A trading order with execution info."""
    symbol: str = ''
    action: OrderAction = OrderAction.BUY
    volume: float = 0.0
    price: float = 0.0
    sl: Optional[float] = None
    tp: Optional[float] = None
    order_type: OrderType = OrderType.MARKET
    comment: str = ''
    magic: int = 0
    ticket: int = 0
    order_id: int = 0


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
    request_id: Optional[str] = None  # For idempotency
    
    def __post_init__(self):
        """Validate order request"""
        if self.volume <= 0:
            raise ValueError("Volume must be positive")
        if self.order_type != OrderType.MARKET and self.price is None:
            raise ValueError("Price required for pending orders")
        if self.sl and self.tp and self.sl == self.tp:
            raise ValueError("SL and TP cannot be equal")
        if self.sl and self.tp:
            if (self.action == OrderAction.BUY and self.sl > self.tp) or \
               (self.action == OrderAction.SELL and self.sl < self.tp):
                raise ValueError("Invalid SL/TP for order direction")


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
        """Get position side"""
        return PositionSide.LONG if self.action == OrderAction.BUY else PositionSide.SHORT
    
    @property
    def pnl_points(self) -> float:
        """Profit/Loss in points"""
        if self.action == OrderAction.BUY:
            return self.price_current - self.price_open
        return self.price_open - self.price_current
    
    @property
    def pnl_percent(self) -> float:
        """Profit/Loss as percentage"""
        if self.price_open == 0:
            return 0
        return (self.pnl_points / self.price_open) * 100
    
    @property
    def is_winning(self) -> bool:
        """Check if position is in profit"""
        return self.profit > 0
    
    @property
    def bars_held(self) -> int:
        """Number of bars held (approximate)"""
        delta = datetime.now() - self.open_time
        return int(delta.total_seconds() / 3600)  # Hours held


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
        """Convert to dictionary"""
        return {
            'time': self.time,
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'close': self.close,
            'volume': self.volume,
            'tick_volume': self.tick_volume,
            'spread': self.spread,
            'real_volume': self.real_volume
        }
    
    @property
    def midpoint(self) -> float:
        """Midpoint of high and low"""
        return (self.high + self.low) / 2
    
    @property
    def range(self) -> float:
        """Price range (high - low)"""
        return self.high - self.low
    
    @property
    def body(self) -> float:
        """Body size (close - open)"""
        return abs(self.close - self.open)
    
    @property
    def is_bullish(self) -> bool:
        """Check if bar is bullish"""
        return self.close > self.open
    
    @property
    def is_bearish(self) -> bool:
        """Check if bar is bearish"""
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
        """Current spread"""
        return self.ask - self.bid
    
    @property
    def midpoint(self) -> float:
        """Midpoint of bid and ask"""
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
        """Check if account is in good standing"""
        return self.free_margin > 0 and (self.margin_level is None or self.margin_level > 100)
    
    @property
    def buying_power(self) -> float:
        """Available buying power"""
        return self.free_margin * self.leverage


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
        """Normalize price to symbol digits"""
        return round(price, self.digits)
    
    def normalize_volume(self, volume: float) -> float:
        """Normalize volume to symbol step"""
        step = self.volume_step
        return round(volume / step) * step
    
    def calculate_pip_value(self, volume: float) -> float:
        """Calculate pip value for a given volume"""
        return self.tick_value * volume / self.tick_size


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
        """Current spread"""
        return self.ask - self.bid
    
    @property
    def midpoint(self) -> float:
        """Midpoint of bid and ask"""
        return (self.bid + self.ask) / 2

@dataclass
class Signal:
    """Trading signal from a strategy."""
    symbol: str = ''
    action: OrderAction = OrderAction.BUY
    volume: float = 0.0
    sl: Optional[float] = None
    tp: Optional[float] = None
    confidence: float = 0.5
    reason: str = ''
