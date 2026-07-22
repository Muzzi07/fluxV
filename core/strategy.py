from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
import pandas as pd
import numpy as np

from fluxV.core.types import (
    Order, Position, Bar, Tick, Signal,
    OrderAction, OrderType, Timeframe
)
from fluxV.core.portfolio import Portfolio


class Strategy(ABC):
    """
    Universal strategy interface that works with all engines:
    - VectorBT (fast ideation)
    - Backtrader (realistic validation)
    - QuantConnect (production deployment)
    - MT5 (live trading)
    """
    
    def __init__(
        self,
        symbols: List[str],
        params: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize strategy
        
        Args:
            symbols: Trading symbols
            params: Strategy parameters
        """
        self.symbols = symbols
        self.params = params or {}
        self.name = self.__class__.__name__
        self.portfolio = Portfolio()
        self._data: Dict[str, pd.DataFrame] = {}
        self._indicators: Dict[str, Any] = {}
        self._positions: Dict[str, List[Position]] = {}
        self._orders: List[Order] = []
        
        # Performance tracking
        self._equity_curve: List[float] = []
        self._trades: List[Dict] = []
        
        # Initialize indicators
        self.init_indicators()
    
    # === Required Methods ===
    
    @abstractmethod
    def init_indicators(self):
        """Initialize indicators - called once at start"""
        pass
    
    @abstractmethod
    def on_bar(self, symbol: str, bar: Bar, context: Dict) -> Optional[List[Order]]:
        """
        Called on each bar for each symbol
        
        Returns:
            List of orders to execute
        """
        pass
    
    @abstractmethod
    def on_tick(self, symbol: str, tick: Tick, context: Dict) -> Optional[List[Order]]:
        """
        Called on each tick for each symbol
        """
        pass
    
    # === Optional Methods ===
    
    def on_start(self, context: Dict):
        """Called when strategy starts"""
        pass
    
    def on_stop(self, context: Dict):
        """Called when strategy stops"""
        pass
    
    def on_position_opened(self, position: Position, context: Dict):
        """Called when a position is opened"""
        pass
    
    def on_position_closed(self, position: Position, context: Dict):
        """Called when a position is closed"""
        pass
    
    def on_order_filled(self, order: Order, context: Dict):
        """Called when an order is filled"""
        pass
    
    # === Helper Methods ===
    
    def get_indicator(self, name: str, symbol: Optional[str] = None) -> Any:
        """Get indicator value"""
        key = f"{symbol}_{name}" if symbol else name
        return self._indicators.get(key)
    
    def set_indicator(self, name: str, value: Any, symbol: Optional[str] = None):
        """Set indicator value"""
        key = f"{symbol}_{name}" if symbol else name
        self._indicators[key] = value
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get current position for symbol"""
        positions = self._positions.get(symbol, [])
        return positions[0] if positions else None
    
    def get_positions(self, symbol: Optional[str] = None) -> List[Position]:
        """Get all positions"""
        if symbol:
            return self._positions.get(symbol, [])
        all_positions = []
        for positions in self._positions.values():
            all_positions.extend(positions)
        return all_positions
    
    def create_order(
        self,
        symbol: str,
        action: OrderAction,
        volume: float,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[float] = None,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        comment: Optional[str] = None
    ) -> Order:
        """Create an order"""
        from fluxV.core.types import Order
        
        order = Order(
            symbol=symbol,
            action=action,
            volume=volume,
            order_type=order_type,
            price=price,
            sl=sl,
            tp=tp,
            comment=comment,
            strategy_name=self.name
        )
        self._orders.append(order)
        return order
    
    def close_position(self, symbol: str) -> Optional[Order]:
        """Create order to close position"""
        position = self.get_position(symbol)
        if position:
            return self.create_order(
                symbol=symbol,
                action=OrderAction.SELL if position.action == OrderAction.BUY else OrderAction.BUY,
                volume=position.volume,
                comment="Close position"
            )
        return None
    
    def close_all_positions(self) -> List[Order]:
        """Close all positions"""
        orders = []
        for symbol in self._positions.keys():
            order = self.close_position(symbol)
            if order:
                orders.append(order)
        return orders
    
    def get_equity(self) -> float:
        """Get current equity"""
        return self.portfolio.total_equity
    
    def get_equity_curve(self) -> List[float]:
        """Get equity curve"""
        return self._equity_curve
    
    def get_trades(self) -> List[Dict]:
        """Get trade history"""
        return self._trades
    
    def record_equity(self):
        """Record current equity for curve"""
        self._equity_curve.append(self.get_equity())
    
    def record_trade(self, trade: Dict):
        """Record a trade"""
        self._trades.append(trade)
    
    def get_params(self) -> Dict:
        """Get strategy parameters"""
        return self.params
    
    def set_params(self, params: Dict):
        """Update strategy parameters"""
        self.params.update(params)


class UniversalStrategy(Strategy):
    """
    Example universal strategy that works with all engines
    """
    
    def __init__(
        self,
        symbols: List[str],
        fast_ma: int = 10,
        slow_ma: int = 30,
        rsi_period: int = 14,
        risk_per_trade: float = 0.02,
        **kwargs
    ):
        self.fast_ma = fast_ma
        self.slow_ma = slow_ma
        self.rsi_period = rsi_period
        self.risk_per_trade = risk_per_trade
        super().__init__(symbols, **kwargs)
    
    def init_indicators(self):
        """Initialize indicators for each symbol"""
        for symbol in self.symbols:
            # Moving averages
            self.set_indicator('fast_ma', None, symbol)
            self.set_indicator('slow_ma', None, symbol)
            self.set_indicator('rsi', None, symbol)
            self.set_indicator('atr', None, symbol)
            
            # Trade state
            self.set_indicator('last_signal', None, symbol)
            self.set_indicator('bar_count', 0, symbol)
    
    def on_bar(self, symbol: str, bar: Bar, context: Dict) -> Optional[List[Order]]:
        """Handle bar event"""
        
        # Update bar count
        bar_count = self.get_indicator('bar_count', symbol) + 1
        self.set_indicator('bar_count', bar_count, symbol)
        
        # Get data for indicators
        bars = context.get('bars', {}).get(symbol, [])
        if len(bars) < max(self.slow_ma, self.rsi_period):
            return None
        
        closes = [b.close for b in bars]
        
        # Calculate indicators
        fast_ma = sum(closes[-self.fast_ma:]) / self.fast_ma
        slow_ma = sum(closes[-self.slow_ma:]) / self.slow_ma
        rsi = self._calculate_rsi(closes, self.rsi_period)
        atr = self._calculate_atr(bars, 14)
        
        # Store indicators
        self.set_indicator('fast_ma', fast_ma, symbol)
        self.set_indicator('slow_ma', slow_ma, symbol)
        self.set_indicator('rsi', rsi, symbol)
        self.set_indicator('atr', atr, symbol)
        
        # Get current position
        position = self.get_position(symbol)
        
        # Risk-based position sizing
        volume = self._calculate_position_size(bar.close, atr, symbol)
        
        # Trading signals
        orders = []
        
        if fast_ma > slow_ma and rsi < 70:
            # Buy signal with trend and RSI confirmation
            if not position:
                # Enter long
                sl = bar.close - atr * 1.5
                tp = bar.close + atr * 2.5
                
                order = self.create_order(
                    symbol=symbol,
                    action=OrderAction.BUY,
                    volume=volume,
                    sl=sl,
                    tp=tp,
                    comment=f"MA Crossover + RSI {rsi:.1f}"
                )
                orders.append(order)
                self.set_indicator('last_signal', 'BUY', symbol)
                
        elif fast_ma < slow_ma and rsi > 30:
            # Sell signal
            if position:
                # Close position
                order = self.close_position(symbol)
                if order:
                    orders.append(order)
                    self.set_indicator('last_signal', 'SELL', symbol)
        
        return orders if orders else None
    
    def on_tick(self, symbol: str, tick: Tick, context: Dict) -> Optional[List[Order]]:
        """Handle tick event - usually for HFT strategies"""
        # Most strategies don't need tick-level logic
        return None
    
    def _calculate_rsi(self, closes: List[float], period: int) -> float:
        """Calculate RSI"""
        if len(closes) < period + 1:
            return 50
        
        gains = 0
        losses = 0
        
        for i in range(1, period + 1):
            change = closes[-i] - closes[-i-1]
            if change > 0:
                gains += change
            else:
                losses -= change
        
        if losses == 0:
            return 100
        
        rs = gains / losses
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def _calculate_atr(self, bars: List[Bar], period: int) -> float:
        """Calculate ATR"""
        if len(bars) < period + 1:
            return 0.001
        
        trs = []
        for i in range(1, period + 1):
            tr = max(
                bars[-i].high - bars[-i].low,
                abs(bars[-i].high - bars[-i-1].close),
                abs(bars[-i].low - bars[-i-1].close)
            )
            trs.append(tr)
        
        return sum(trs) / period
    
    def _calculate_position_size(self, price: float, atr: float, symbol: str) -> float:
        """Calculate position size based on risk"""
        # Risk in account currency
        risk_capital = self.portfolio.total_equity * self.risk_per_trade
        
        # Risk per unit
        risk_per_unit = atr
        
        # Position size
        if risk_per_unit > 0:
            volume = risk_capital / (risk_per_unit * 100000)  # Standard lot
        else:
            volume = 0.01
        
        # Round to lot size
        volume = round(volume * 100) / 100
        volume = max(0.01, min(volume, 10.0))
        
        return volume