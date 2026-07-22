"""
Async mock broker for backtesting simulation
"""
import asyncio
from typing import Optional, List, Dict, Any, AsyncIterator, Callable, Awaitable
from datetime import datetime
import pandas as pd
import numpy as np
import logging
from collections import defaultdict

from fluxV.core.broker import Broker
from fluxV.core.types import (
    OrderRequest, OrderResult, Position, Bar, Tick, AccountInfo,
    SymbolInfo, OrderAction, OrderType, Timeframe, OrderStatus,
    MarketSnapshot
)
from fluxV.core.exceptions import (
    OrderError, SymbolNotFoundError, InsufficientBalanceError
)

logger = logging.getLogger(__name__)


class MockBroker(Broker):
    """
    Async mock broker for backtesting. Simulates order execution,
    portfolio tracking, and uses local data files.
    All operations are async but internally synchronous.
    """
    
    def __init__(
        self,
        initial_balance: float = 10000,
        commission: float = 0.0,
        slippage: float = 0.0,
        spread: float = 0.0002,
        leverage: int = 100,
        currency: str = "USD"
    ):
        """
        Initialize mock broker.
        
        Args:
            initial_balance: Starting account balance
            commission: Commission per unit (e.g., 0.001 for 0.1% of volume)
            slippage: Slippage in points
            spread: Spread to apply (default 0.0002 for EURUSD)
            leverage: Account leverage
            currency: Account currency
        """
        self._mode = "backtest"
        self._connected = True
        self._initial_balance = initial_balance
        self._balance = initial_balance
        self._equity = initial_balance
        self._commission = commission
        self._slippage = slippage
        self._spread = spread
        self._leverage = leverage
        self._currency = currency
        
        self._positions: Dict[int, Position] = {}
        self._position_counter = 0
        self._pending_orders: Dict[int, OrderResult] = {}
        self._order_counter = 0
        self._data_cache: Dict[str, pd.DataFrame] = {}
        self._symbol_info_cache: Dict[str, SymbolInfo] = {}
        self._current_time: Optional[datetime] = None
        self._current_prices: Dict[str, float] = {}
        self._market_snapshots: Dict[str, MarketSnapshot] = {}
        
        # Performance tracking
        self._trade_history: List[Dict] = []
        self._equity_curve: List[Dict] = []
        self._bars_processed = 0
        self._orders_placed = 0
        self._orders_filled = 0
        self._orders_rejected = 0
        
        # Streaming state
        self._streaming = False
        self._stream_tasks: List[asyncio.Task] = []
        
        # Order tracking for async waiting
        self._order_events: Dict[int, asyncio.Event] = {}
        self._order_results: Dict[int, OrderResult] = {}
    
    async def connect(self, **kwargs) -> bool:
        """Mock connect - always succeeds"""
        self._connected = True
        self._balance = self._initial_balance
        self._equity = self._initial_balance
        return True
    
    async def disconnect(self) -> bool:
        """Mock disconnect"""
        self._connected = False
        return True
    
    async def is_connected(self) -> bool:
        """Always connected in backtest mode"""
        return self._connected
    
    async def get_account_info(self) -> AccountInfo:
        """Get simulated account info"""
        total_profit = sum(pos.profit for pos in self._positions.values())
        self._equity = self._balance + total_profit
        
        return AccountInfo(
            balance=self._balance,
            equity=self._equity,
            margin=0.0,
            free_margin=self._equity,
            leverage=self._leverage,
            currency=self._currency,
            profit=total_profit,
            margin_level=float('inf') if self._equity > 0 else 0,
            trade_allowed=True
        )
    
    async def get_symbol_info(self, symbol: str) -> Optional[SymbolInfo]:
        """Get symbol information"""
        if symbol in self._symbol_info_cache:
            return self._symbol_info_cache[symbol]
        
        # Create default symbol info for backtesting
        info = SymbolInfo(
            name=symbol,
            digits=5,
            point=0.00001,
            min_volume=0.01,
            max_volume=100,
            volume_step=0.01,
            trade_contract_size=100000,
            spread=20,
            tick_size=0.00001,
            tick_value=1.0,
            is_tradable=True,
            is_visible=True
        )
        self._symbol_info_cache[symbol] = info
        return info
    
    def set_current_time(self, dt: datetime):
        """Set the current simulation time for look-ahead prevention"""
        self._current_time = dt
    
    def set_current_price(self, symbol: str, price: float):
        """Set the current price for a symbol"""
        self._current_prices[symbol] = price
        
        # Update market snapshot
        if symbol in self._market_snapshots:
            self._market_snapshots[symbol].timestamp = self._current_time or datetime.now()
            self._market_snapshots[symbol].bid = price - self._spread/2
            self._market_snapshots[symbol].ask = price + self._spread/2
            self._market_snapshots[symbol].last = price
        
        # Update positions with current price
        for pos in self._positions.values():
            if pos.symbol == symbol:
                pos.price_current = price
                if pos.action == OrderAction.BUY:
                    pos.profit = (price - pos.price_open) * pos.volume
                else:
                    pos.profit = (pos.price_open - price) * pos.volume
    
    def load_data(self, symbol: str, timeframe: Timeframe, 
                  data: pd.DataFrame):
        """
        Load historical data for backtesting.
        
        Args:
            symbol: Trading symbol
            timeframe: Timeframe of the data
            data: DataFrame with columns: time, open, high, low, close, volume
        """
        required_cols = ['time', 'open', 'high', 'low', 'close']
        if not all(col in data.columns for col in required_cols):
            raise ValueError(f"Data must have columns: {required_cols}")
        
        # Ensure time is datetime
        if not pd.api.types.is_datetime64_any_dtype(data['time']):
            data['time'] = pd.to_datetime(data['time'])
        
        # Add volume if not present
        if 'volume' not in data.columns:
            data['volume'] = 0
        
        self._data_cache[f"{symbol}_{timeframe.value}"] = data
        
        # Initialize market snapshot
        if len(data) > 0:
            self._market_snapshots[symbol] = MarketSnapshot(
                symbol=symbol,
                timestamp=data['time'].iloc[0],
                bid=data['close'].iloc[0] - self._spread/2,
                ask=data['close'].iloc[0] + self._spread/2,
                last=data['close'].iloc[0],
                volume=int(data['volume'].iloc[0]) if data['volume'].iloc[0] else 0
            )
    
    async def get_rates(
        self, 
        symbol: str, 
        timeframe: Timeframe,
        from_date: datetime,
        to_date: datetime
    ) -> List[Bar]:
        """Get historical rates from cached data"""
        key = f"{symbol}_{timeframe.value}"
        if key not in self._data_cache:
            raise SymbolNotFoundError(f"No data loaded for {symbol} {timeframe}")
        
        df = self._data_cache[key]
        mask = (df['time'] >= from_date) & (df['time'] <= to_date)
        subset = df[mask]
        
        if len(subset) == 0:
            return []
        
        return [
            Bar(
                time=row['time'].to_pydatetime(),
                open=float(row['open']),
                high=float(row['high']),
                low=float(row['low']),
                close=float(row['close']),
                volume=int(row['volume']) if row['volume'] else 0
            )
            for _, row in subset.iterrows()
        ]
    
    async def get_rates_latest(
        self, 
        symbol: str, 
        timeframe: Timeframe,
        count: int
    ) -> List[Bar]:
        """Get the most recent n bars from cached data"""
        key = f"{symbol}_{timeframe.value}"
        if key not in self._data_cache:
            raise SymbolNotFoundError(f"No data loaded for {symbol} {timeframe}")
        
        df = self._data_cache[key]
        
        # Only use data up to current simulation time
        if self._current_time:
            df = df[df['time'] <= self._current_time]
        
        subset = df.tail(count)
        
        if len(subset) == 0:
            return []
        
        return [
            Bar(
                time=row['time'].to_pydatetime(),
                open=float(row['open']),
                high=float(row['high']),
                low=float(row['low']),
                close=float(row['close']),
                volume=int(row['volume']) if row['volume'] else 0
            )
            for _, row in subset.iterrows()
        ]
    
    async def stream_rates(
        self,
        symbol: str,
        timeframe: Timeframe,
        callback: Optional[Callable[[Bar], Awaitable[None]]] = None
    ) -> AsyncIterator[Bar]:
        """
        Stream bars during backtest simulation.
        """
        key = f"{symbol}_{timeframe.value}"
        if key not in self._data_cache:
            raise SymbolNotFoundError(f"No data loaded for {symbol} {timeframe}")
        
        df = self._data_cache[key]
        self._streaming = True
        
        for _, row in df.iterrows():
            if not self._streaming:
                break
            
            bar = Bar(
                time=row['time'].to_pydatetime(),
                open=float(row['open']),
                high=float(row['high']),
                low=float(row['low']),
                close=float(row['close']),
                volume=int(row['volume']) if row['volume'] else 0
            )
            
            self.set_current_time(bar.time)
            self.set_current_price(symbol, bar.close)
            
            if callback:
                await callback(bar)
            
            yield bar
            
            # Simulate time passing
            await asyncio.sleep(0.01)  # Small delay for simulation
    
    async def stream_ticks(
        self,
        symbol: str,
        callback: Optional[Callable[[Tick], Awaitable[None]]] = None
    ) -> AsyncIterator[Tick]:
        """
        Stream ticks during backtest simulation.
        """
        # For backtesting, we simulate ticks from bars
        key = f"{symbol}_{Timeframe.D1.value}"
        if key not in self._data_cache:
            raise SymbolNotFoundError(f"No data loaded for {symbol}")
        
        df = self._data_cache[key]
        self._streaming = True
        
        for _, row in df.iterrows():
            if not self._streaming:
                break
            
            # Generate simulated ticks (5 ticks per bar)
            for i in range(5):
                tick = Tick(
                    time=row['time'].to_pydatetime(),
                    bid=float(row['low'] + (row['high'] - row['low']) * (i/5)),
                    ask=float(row['low'] + (row['high'] - row['low']) * (i/5) + self._spread),
                    last=float(row['close']),
                    volume=int(row['volume']) if row['volume'] else 0,
                    flags=0
                )
                
                self.set_current_price(symbol, tick.midpoint)
                
                if callback:
                    await callback(tick)
                
                yield tick
                await asyncio.sleep(0.001)  # Very small delay
    
    async def get_snapshot(self, symbol: str) -> MarketSnapshot:
        """Get current market snapshot"""
        if symbol not in self._market_snapshots:
            raise SymbolNotFoundError(f"No data for {symbol}")
        
        snapshot = self._market_snapshots[symbol]
        snapshot.timestamp = self._current_time or datetime.now()
        return snapshot
    
    async def place_order(self, request: OrderRequest) -> OrderResult:
        """
        Simulate placing an order for backtesting.
        """
        self._orders_placed += 1
        
        # Validate order
        if request.volume <= 0:
            self._orders_rejected += 1
            raise OrderError("Volume must be positive")
        
        # Get current price
        current_price = self._get_current_price(request.symbol)
        if current_price is None:
            self._orders_rejected += 1
            raise OrderError(f"Cannot get price for {request.symbol}")
        
        # Calculate margin requirement
        margin_required = current_price * request.volume * 0.01
        if margin_required > self._balance:
            self._orders_rejected += 1
            raise InsufficientBalanceError(
                f"Insufficient balance: required {margin_required:.2f}, "
                f"available {self._balance:.2f}"
            )
        
        # Generate order ID
        self._order_counter += 1
        order_id = self._order_counter
        
        # For market orders, execute immediately
        if request.order_type == OrderType.MARKET:
            execution_price = self._get_execution_price(request, current_price)
            
            # Calculate commission
            commission = request.volume * self._commission
            
            # Create position
            self._position_counter += 1
            position = Position(
                ticket=self._position_counter,
                symbol=request.symbol,
                action=request.action,
                volume=request.volume,
                price_open=execution_price,
                price_current=execution_price,
                sl=request.sl or 0,
                tp=request.tp or 0,
                profit=0,
                comment=request.comment,
                magic=request.magic,
                open_time=self._current_time or datetime.now(),
                commission=commission
            )
            
            self._positions[position.ticket] = position
            self._orders_filled += 1
            
            result = OrderResult(
                order_id=order_id,
                symbol=request.symbol,
                action=request.action,
                volume=request.volume,
                price=execution_price,
                sl=request.sl,
                tp=request.tp,
                comment=request.comment,
                status=OrderStatus.FILLED,
                magic=request.magic,
                filled_volume=request.volume,
                created_time=self._current_time or datetime.now(),
                filled_time=self._current_time or datetime.now()
            )
            
            return result
        
        # For pending orders, store them
        else:
            if request.price is None:
                self._orders_rejected += 1
                raise OrderError("Price required for pending order")
            
            result = OrderResult(
                order_id=order_id,
                symbol=request.symbol,
                action=request.action,
                volume=request.volume,
                price=request.price,
                sl=request.sl,
                tp=request.tp,
                comment=request.comment,
                status=OrderStatus.PENDING,
                magic=request.magic,
                remaining_volume=request.volume,
                created_time=self._current_time or datetime.now()
            )
            self._pending_orders[order_id] = result
            self._order_events[order_id] = asyncio.Event()
            
            return result
    
    async def close_position(self, ticket: int) -> bool:
        """Close a position"""
        if ticket not in self._positions:
            return False
        
        position = self._positions[ticket]
        current_price = self._get_current_price(position.symbol)
        
        if current_price is None:
            return False
        
        # Calculate profit
        if position.action == OrderAction.BUY:
            profit = (current_price - position.price_open) * position.volume
        else:
            profit = (position.price_open - current_price) * position.volume
        
        # Subtract commission
        profit -= position.volume * self._commission
        
        # Update balance
        self._balance += profit
        
        # Record trade
        self._trade_history.append({
            'ticket': ticket,
            'symbol': position.symbol,
            'action': position.action.value,
            'volume': position.volume,
            'price_open': position.price_open,
            'price_close': current_price,
            'profit': profit,
            'commission': position.volume * self._commission,
            'open_time': position.open_time,
            'close_time': self._current_time or datetime.now(),
            'bars_held': (self._current_time - position.open_time).total_seconds() / 3600 if self._current_time else 0
        })
        
        # Remove position
        del self._positions[ticket]
        
        return True
    
    async def close_all_positions(self, symbol: Optional[str] = None) -> bool:
        """Close all positions, optionally filtered by symbol"""
        positions_to_close = []
        for ticket, pos in self._positions.items():
            if symbol is None or pos.symbol == symbol:
                positions_to_close.append(ticket)
        
        # Use TaskGroup for concurrent closing
        try:
            async with asyncio.TaskGroup() as tg:
                tasks = []
                for ticket in positions_to_close:
                    task = tg.create_task(self.close_position(ticket))
                    tasks.append(task)
                return all(task.result() for task in tasks)
        except ExceptionGroup as e:
            logger.error(f"Error closing positions: {e}")
            return False
    
    async def get_positions(self, symbol: Optional[str] = None) -> List[Position]:
        """Get all open positions"""
        if symbol:
            return [pos for pos in self._positions.values() if pos.symbol == symbol]
        return list(self._positions.values())
    
    async def modify_position(
        self, 
        ticket: int, 
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        trailing_stop: Optional[float] = None
    ) -> bool:
        """Modify stop loss and take profit for a position"""
        if ticket not in self._positions:
            return False
        
        if sl is not None:
            self._positions[ticket].sl = sl
        if tp is not None:
            self._positions[ticket].tp = tp
        
        # Handle trailing stop
        if trailing_stop is not None:
            position = self._positions[ticket]
            current_price = self._get_current_price(position.symbol)
            if position.action == OrderAction.BUY:
                new_sl = current_price - trailing_stop
            else:
                new_sl = current_price + trailing_stop
            self._positions[ticket].sl = new_sl
        
        return True
    
    async def get_pending_orders(self, symbol: Optional[str] = None) -> List[OrderResult]:
        """Get all pending orders"""
        if symbol:
            return [order for order in self._pending_orders.values() 
                   if order.symbol == symbol]
        return list(self._pending_orders.values())
    
    async def cancel_order(self, ticket: int) -> bool:
        """Cancel a pending order"""
        if ticket in self._pending_orders:
            self._pending_orders[ticket].status = OrderStatus.CANCELLED
            del self._pending_orders[ticket]
            self._order_events.pop(ticket, None)
            return True
        return False
    
    async def cancel_all_orders(self, symbol: Optional[str] = None) -> bool:
        """Cancel all pending orders"""
        orders = await self.get_pending_orders(symbol)
        for order in orders:
            await self.cancel_order(order.order_id)
        return True
    
    def get_mode(self) -> str:
        """Return the current mode"""
        return self._mode
    
    async def wait_for_order_fill(self, order_id: int, timeout: float = 30.0) -> OrderResult:
        """Wait for an order to be filled"""
        if order_id not in self._order_events:
            # Check if already filled
            if order_id in self._pending_orders:
                # Still pending
                pass
            else:
                raise OrderError(f"Order {order_id} not found")
        
        try:
            async with asyncio.timeout(timeout):
                await self._order_events[order_id].wait()
                return self._order_results.get(order_id)
        except asyncio.TimeoutError:
            raise TimeoutError(f"Order {order_id} did not fill within {timeout}s")
    
    # Backtesting specific methods
    def update_positions(self, current_price: float):
        """Update current price of all positions"""
        for position in self._positions.values():
            position.price_current = current_price
            if position.action == OrderAction.BUY:
                position.profit = (current_price - position.price_open) * position.volume
            else:
                position.profit = (position.price_open - current_price) * position.volume
    
    def check_stops(self, symbol: str, high: float, low: float):
        """
        Check if any stop loss or take profit levels have been hit.
        """
        for ticket, position in list(self._positions.items()):
            if position.symbol != symbol:
                continue
            
            # Check stop loss
            if position.action == OrderAction.BUY:
                if position.sl and low <= position.sl:
                    self._close_position_at_price(ticket, position.sl)
                elif position.tp and high >= position.tp:
                    self._close_position_at_price(ticket, position.tp)
            else:  # SELL
                if position.sl and high >= position.sl:
                    self._close_position_at_price(ticket, position.sl)
                elif position.tp and low <= position.tp:
                    self._close_position_at_price(ticket, position.tp)
    
    def check_pending_orders(self, symbol: str, high: float, low: float):
        """
        Check if any pending orders should be triggered.
        """
        for order_id, order in list(self._pending_orders.items()):
            if order.symbol != symbol:
                continue
            
            trigger_price = order.price
            
            # Check if order should be triggered
            triggered = False
            execution_price = trigger_price
            
            if order.action == OrderAction.BUY:
                if order.order_type == OrderType.LIMIT and low <= trigger_price:
                    triggered = True
                elif order.order_type == OrderType.STOP and high >= trigger_price:
                    triggered = True
            else:  # SELL
                if order.order_type == OrderType.LIMIT and high >= trigger_price:
                    triggered = True
                elif order.order_type == OrderType.STOP and low <= trigger_price:
                    triggered = True
            
            if triggered:
                # Execute the pending order
                request = OrderRequest(
                    symbol=order.symbol,
                    action=order.action,
                    volume=order.volume,
                    order_type=OrderType.MARKET,
                    sl=order.sl,
                    tp=order.tp,
                    comment=order.comment,
                    magic=order.magic
                )
                
                try:
                    # Execute synchronously for simplicity
                    result = asyncio.run(self.place_order(request))
                    # Remove pending order
                    del self._pending_orders[order_id]
                    # Signal order fill
                    if order_id in self._order_events:
                        self._order_results[order_id] = result
                        self._order_events[order_id].set()
                except Exception as e:
                    logger.error(f"Failed to execute pending order {order_id}: {e}")
    
    def record_equity(self):
        """Record current equity for the equity curve"""
        total_profit = sum(pos.profit for pos in self._positions.values())
        equity = self._balance + total_profit
        
        self._equity_curve.append({
            'time': self._current_time,
            'balance': self._balance,
            'equity': equity,
            'profit': total_profit,
            'positions': len(self._positions)
        })
    
    def get_equity_curve(self) -> pd.DataFrame:
        """Get the equity curve from backtesting"""
        return pd.DataFrame(self._equity_curve)
    
    def get_trade_history(self) -> pd.DataFrame:
        """Get the trade history from backtesting"""
        return pd.DataFrame(self._trade_history)
    
    def get_stats(self) -> Dict:
        """Get backtesting statistics"""
        if len(self._trade_history) == 0:
            win_rate = 0
        else:
            win_rate = len([t for t in self._trade_history if t['profit'] > 0]) / len(self._trade_history) * 100
        
        return {
            'initial_balance': self._initial_balance,
            'final_balance': self._balance,
            'total_profit': self._balance - self._initial_balance,
            'total_trades': len(self._trade_history),
            'winning_trades': len([t for t in self._trade_history if t['profit'] > 0]),
            'losing_trades': len([t for t in self._trade_history if t['profit'] < 0]),
            'win_rate': win_rate,
            'total_commission': sum(t['commission'] for t in self._trade_history),
            'max_drawdown': self._calculate_max_drawdown(),
            'bars_processed': self._bars_processed,
            'orders_placed': self._orders_placed,
            'orders_filled': self._orders_filled,
            'orders_rejected': self._orders_rejected
        }
    
    def reset(self):
        """Reset the broker to initial state"""
        self._balance = self._initial_balance
        self._equity = self._initial_balance
        self._positions = {}
        self._position_counter = 0
        self._pending_orders = {}
        self._order_counter = 0
        self._trade_history = []
        self._equity_curve = []
        self._bars_processed = 0
        self._orders_placed = 0
        self._orders_filled = 0
        self._orders_rejected = 0
        self._order_events = {}
        self._order_results = {}
    
    # Private helper methods
    def _get_current_price(self, symbol: str) -> Optional[float]:
        """Get the current price for a symbol"""
        # Check if we have a current price set
        if symbol in self._current_prices:
            return self._current_prices[symbol]
        
        # Try to get from data cache
        key = f"{symbol}_{Timeframe.D1.value}"
        if key in self._data_cache:
            df = self._data_cache[key]
            if self._current_time:
                df = df[df['time'] <= self._current_time]
            if len(df) > 0:
                return df.iloc[-1]['close']
        
        return None
    
    def _get_execution_price(self, request: OrderRequest, current_price: float) -> float:
        """Get execution price with slippage"""
        if request.action == OrderAction.BUY:
            price = current_price + self._spread
            price += self._slippage
        else:
            price = current_price
            price -= self._slippage
        
        return price
    
    def _close_position_at_price(self, ticket: int, price: float):
        """Close a position at a specific price (for stop loss/take profit)"""
        if ticket not in self._positions:
            return
        
        position = self._positions[ticket]
        
        # Calculate profit at the stop/tp price
        if position.action == OrderAction.BUY:
            profit = (price - position.price_open) * position.volume
        else:
            profit = (position.price_open - price) * position.volume
        
        # Subtract commission
        profit -= position.volume * self._commission
        
        # Update balance
        self._balance += profit
        
        # Record trade
        close_reason = 'stop_loss' if (position.sl and price == position.sl) else 'take_profit'
        
        self._trade_history.append({
            'ticket': ticket,
            'symbol': position.symbol,
            'action': position.action.value,
            'volume': position.volume,
            'price_open': position.price_open,
            'price_close': price,
            'profit': profit,
            'commission': position.volume * self._commission,
            'open_time': position.open_time,
            'close_time': self._current_time or datetime.now(),
            'close_reason': close_reason,
            'bars_held': (self._current_time - position.open_time).total_seconds() / 3600 if self._current_time else 0
        })
        
        # Remove position
        del self._positions[ticket]
    
    def _calculate_max_drawdown(self) -> float:
        """Calculate maximum drawdown from equity curve"""
        if len(self._equity_curve) < 2:
            return 0
        
        equities = [e['equity'] for e in self._equity_curve]
        peak = equities[0]
        max_drawdown = 0
        
        for equity in equities:
            if equity > peak:
                peak = equity
            drawdown = (peak - equity) / peak * 100 if peak > 0 else 0
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        return max_drawdown