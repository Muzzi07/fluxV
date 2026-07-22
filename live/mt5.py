import asyncio
import MetaTrader5 as mt5
from typing import Optional, List, Dict, Any, AsyncIterator, Callable, Awaitable
from datetime import datetime
import time
import logging
from contextlib import asynccontextmanager

from fluxV.core.broker import Broker
from fluxV.core.types import (
    OrderRequest, OrderResult, Position, Bar, Tick, AccountInfo,
    SymbolInfo, OrderAction, OrderType, Timeframe, OrderStatus,
    MarketSnapshot
)
from fluxV.core.exceptions import (
    ConnectionError, OrderError, SymbolNotFoundError,
    InsufficientBalanceError, MarketClosedError, TimeoutError
)
from fluxV.utils.retry import async_retry
from fluxV.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class MT5Broker(Broker):
    """
    Async live broker implementation using MetaTrader5 package.
    Uses asyncio to prevent blocking operations.
    """
    
    def __init__(
        self,
        auto_connect: bool = False,
        max_retries: int = 3,
        retry_delay: float = 0.5,
        order_timeout: float = 30.0,
        **kwargs
    ):
        """
        Initialize MT5 broker.
        
        Args:
            auto_connect: If True, connect immediately
            max_retries: Maximum retry attempts for failed operations
            retry_delay: Delay between retries
            order_timeout: Timeout for order operations
            **kwargs: Connection parameters
        """
        self._connected = False
        self._mode = "live"
        self._symbol_info_cache = {}
        self._symbol_tick_cache = {}
        self._connection_params = kwargs
        self._last_order_time = 0
        self._min_order_interval = 0.1
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._order_timeout = order_timeout
        self._rate_limiter = RateLimiter(rate=10, per=1.0)  # 10 requests per second
        
        # Order tracking
        self._pending_orders: Dict[int, asyncio.Future] = {}
        self._order_futures: Dict[int, asyncio.Future] = {}
        
        # Streaming state
        self._streaming = False
        self._stream_tasks: List[asyncio.Task] = []
        
        # Connection lock
        self._connection_lock = asyncio.Lock()
        
        if auto_connect:
            asyncio.create_task(self.connect(**kwargs))
    
    @async_retry(max_attempts=3, delay=0.5, exceptions=(ConnectionError,))
    async def connect(self, login: int = None, password: str = None, 
                      server: str = None, path: str = None) -> bool:
        """
        Connect to MT5 terminal asynchronously.
        """
        async with self._connection_lock:
            # Use stored params if not provided
            login = login or self._connection_params.get('login')
            password = password or self._connection_params.get('password')
            server = server or self._connection_params.get('server')
            path = path or self._connection_params.get('path')
            
            # Run MT5 initialization in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            initialized = await loop.run_in_executor(
                None, mt5.initialize, path
            )
            
            if not initialized:
                error = mt5.last_error()
                raise ConnectionError(f"Failed to initialize MT5: {error}")
            
            # Login if credentials provided
            if login and password and server:
                authorized = await loop.run_in_executor(
                    None, mt5.login, login, password, server
                )
                if not authorized:
                    error = mt5.last_error()
                    await self._shutdown_mt5()
                    raise ConnectionError(f"Failed to login: {error}")
            elif login or password or server:
                await self._shutdown_mt5()
                raise ConnectionError("Incomplete login credentials")
            
            # Verify connection
            terminal_info = await loop.run_in_executor(None, mt5.terminal_info)
            if not terminal_info:
                await self._shutdown_mt5()
                raise ConnectionError("Failed to get terminal info")
            
            self._connected = True
            logger.info(f"Connected to MT5 terminal v{terminal_info.version}")
            return True
    
    async def disconnect(self) -> bool:
        """Disconnect from MT5 terminal"""
        if self._connected:
            # Cancel any streaming tasks
            for task in self._stream_tasks:
                task.cancel()
            
            # Shutdown MT5 in thread pool
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, mt5.shutdown)
            self._connected = False
            
            # Cancel any pending order futures
            for future in self._order_futures.values():
                future.cancel()
            
            logger.info("Disconnected from MT5")
        return True
    
    async def _shutdown_mt5(self):
        """Shutdown MT5 connection"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, mt5.shutdown)
        self._connected = False
    
    async def is_connected(self) -> bool:
        """Check if connected to MT5"""
        if not self._connected:
            return False
        try:
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, mt5.terminal_info)
            return info is not None
        except Exception:
            return False
    
    @async_retry(max_attempts=3, delay=0.1)
    async def get_account_info(self) -> AccountInfo:
        """Get current account information"""
        await self._ensure_connected()
        await self._rate_limiter.acquire()
        
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, mt5.account_info)
        
        if not info:
            raise ConnectionError(f"Failed to get account info: {mt5.last_error()}")
        
        return AccountInfo(
            balance=info.balance,
            equity=info.equity,
            margin=info.margin,
            free_margin=info.margin_free,
            leverage=info.leverage,
            currency=info.currency,
            profit=info.profit,
            margin_level=info.margin_level,
            server=info.server,
            name=info.name,
            company=info.company,
            trade_allowed=info.trade_allowed
        )
    
    @async_retry(max_attempts=2, delay=0.1)
    async def get_symbol_info(self, symbol: str) -> Optional[SymbolInfo]:
        """Get symbol information"""
        await self._ensure_connected()
        
        if symbol not in self._symbol_info_cache:
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, mt5.symbol_info, symbol)
            if info:
                self._symbol_info_cache[symbol] = info
        
        info = self._symbol_info_cache.get(symbol)
        if not info:
            return None
        
        return SymbolInfo(
            name=info.name,
            digits=info.digits,
            point=info.point,
            min_volume=info.volume_min,
            max_volume=info.volume_max,
            volume_step=info.volume_step,
            trade_contract_size=info.trade_contract_size,
            spread=info.spread,
            tick_size=info.tick_size,
            tick_value=info.tick_value,
            description=info.description,
            is_tradable=info.trade_mode != mt5.SYMBOL_TRADE_MODE_DISABLED,
            is_visible=info.visible,
            path=info.path
        )
    
    @async_retry(max_attempts=3, delay=0.2)
    async def get_rates(
        self, 
        symbol: str, 
        timeframe: Timeframe,
        from_date: datetime,
        to_date: datetime
    ) -> List[Bar]:
        """Get historical rates asynchronously"""
        await self._ensure_connected()
        await self._ensure_symbol_available(symbol)
        await self._rate_limiter.acquire()
        
        loop = asyncio.get_event_loop()
        rates = await loop.run_in_executor(
            None, mt5.copy_rates_range, symbol, timeframe.value, from_date, to_date
        )
        
        if rates is None or len(rates) == 0:
            return []
        
        return self._convert_rates_to_bars(rates)
    
    @async_retry(max_attempts=3, delay=0.1)
    async def get_rates_latest(
        self, 
        symbol: str, 
        timeframe: Timeframe,
        count: int
    ) -> List[Bar]:
        """Get the most recent n bars asynchronously"""
        await self._ensure_connected()
        await self._ensure_symbol_available(symbol)
        await self._rate_limiter.acquire()
        
        loop = asyncio.get_event_loop()
        rates = await loop.run_in_executor(
            None, mt5.copy_rates_from_pos, symbol, timeframe.value, 0, count
        )
        
        if rates is None or len(rates) == 0:
            return []
        
        return self._convert_rates_to_bars(rates)
    
    async def stream_rates(
        self,
        symbol: str,
        timeframe: Timeframe,
        callback: Optional[Callable[[Bar], Awaitable[None]]] = None
    ) -> AsyncIterator[Bar]:
        """
        Stream real-time bars.
        
        This is a generator that yields bars as they arrive.
        """
        await self._ensure_connected()
        await self._ensure_symbol_available(symbol)
        
        # Get initial bar
        bars = await self.get_rates_latest(symbol, timeframe, 1)
        if not bars:
            raise ValueError(f"No bars available for {symbol}")
        
        current_bar_time = bars[0].time
        self._streaming = True
        
        try:
            while self._streaming:
                # Check for new bar
                new_bars = await self.get_rates_latest(symbol, timeframe, 2)
                if len(new_bars) >= 2:
                    # Check if we have a new bar
                    if new_bars[-1].time > current_bar_time:
                        bar = new_bars[-1]
                        current_bar_time = bar.time
                        
                        if callback:
                            await callback(bar)
                        yield bar
                
                # Wait for next check
                await asyncio.sleep(1)  # Check every second
                
        except asyncio.CancelledError:
            self._streaming = False
            raise
    
    async def stream_ticks(
        self,
        symbol: str,
        callback: Optional[Callable[[Tick], Awaitable[None]]] = None
    ) -> AsyncIterator[Tick]:
        """
        Stream real-time ticks.
        
        This is a generator that yields ticks as they arrive.
        """
        await self._ensure_connected()
        await self._ensure_symbol_available(symbol)
        
        self._streaming = True
        
        # Keep track of last tick time to avoid duplicates
        last_tick_time = None
        
        try:
            while self._streaming:
                tick = await self._get_current_tick(symbol)
                
                # Only yield if tick is new
                if tick and (last_tick_time is None or tick.time > last_tick_time):
                    last_tick_time = tick.time
                    
                    if callback:
                        await callback(tick)
                    yield tick
                
                # Small delay to prevent CPU spinning
                await asyncio.sleep(0.1)  # 100ms between ticks
                
        except asyncio.CancelledError:
            self._streaming = False
            raise
    
    @async_retry(max_attempts=2, delay=0.05)
    async def get_snapshot(self, symbol: str) -> MarketSnapshot:
        """Get current market snapshot"""
        await self._ensure_connected()
        await self._ensure_symbol_available(symbol)
        
        tick = await self._get_current_tick(symbol)
        if not tick:
            raise SymbolNotFoundError(f"Cannot get tick for {symbol}")
        
        return MarketSnapshot(
            symbol=symbol,
            timestamp=tick.time,
            bid=tick.bid,
            ask=tick.ask,
            last=tick.last,
            volume=tick.volume
        )
    
    @async_retry(max_attempts=3, delay=0.1)
    async def place_order(self, request: OrderRequest) -> OrderResult:
        """
        Place an order asynchronously.
        Uses futures for non-blocking order monitoring.
        """
        await self._ensure_connected()
        await self._ensure_symbol_available(request.symbol)
        await self._rate_limiter.acquire()
        
        # Rate limiting
        current_time = time.time()
        if current_time - self._last_order_time < self._min_order_interval:
            await asyncio.sleep(self._min_order_interval - (current_time - self._last_order_time))
        
        # Get symbol info
        symbol_info = await self.get_symbol_info(request.symbol)
        if not symbol_info:
            raise SymbolNotFoundError(f"Symbol {request.symbol} not found")
        
        # Check if market is open
        if not await self._is_market_open(request.symbol):
            raise MarketClosedError(f"Market is closed for {request.symbol}")
        
        # Normalize volume and price
        volume = symbol_info.normalize_volume(request.volume)
        
        # Get current price
        tick = await self._get_current_tick(request.symbol)
        if not tick:
            raise OrderError(f"Cannot get tick for {request.symbol}")
        
        # Build order request
        order_type, order_type_str = self._get_mt5_order_type(request)
        price = self._get_order_price(request, tick)
        
        # Normalize SL and TP
        sl = symbol_info.normalize_price(request.sl) if request.sl else 0
        tp = symbol_info.normalize_price(request.tp) if request.tp else 0
        
        # Prepare MT5 request
        mt5_request = {
            "action": mt5.TRADE_ACTION_DEAL if request.order_type == OrderType.MARKET 
                      else mt5.TRADE_ACTION_PENDING,
            "symbol": request.symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "comment": request.comment or "",
            "magic": request.magic or 0,
            "deviation": request.deviation,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC
        }
        
        # For pending orders
        if request.order_type != OrderType.MARKET:
            mt5_request["stop_limit"] = 0
            mt5_request["expiration"] = int(request.expiration.timestamp()) if request.expiration else 0
        
        # Send order in thread pool
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, mt5.order_send, mt5_request)
        self._last_order_time = time.time()
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            error_msg = f"Order failed: {result.comment} (code: {result.retcode})"
            if result.retcode == mt5.TRADE_RETCODE_INSUFFICIENT_MONEY:
                raise InsufficientBalanceError(error_msg)
            raise OrderError(error_msg)
        
        # Create result
        order_result = OrderResult(
            order_id=result.order,
            symbol=request.symbol,
            action=request.action,
            volume=volume,
            price=result.price,
            sl=request.sl,
            tp=request.tp,
            comment=request.comment,
            status=OrderStatus.FILLED if request.order_type == OrderType.MARKET 
                   else OrderStatus.PENDING,
            magic=request.magic,
            message=result.comment,
            filled_volume=volume if request.order_type == OrderType.MARKET else 0,
            remaining_volume=volume if request.order_type != OrderType.MARKET else 0
        )
        
        # If order is pending, create future for monitoring
        if request.order_type != OrderType.MARKET:
            future = asyncio.get_event_loop().create_future()
            self._order_futures[result.order] = future
        
        return order_result
    
    async def wait_for_order_fill(self, order_id: int, timeout: float = 30.0) -> OrderResult:
        """
        Wait for an order to be filled asynchronously.
        """
        if order_id not in self._order_futures:
            # Check if order is already filled
            orders = await self.get_pending_orders()
            for order in orders:
                if order.order_id == order_id:
                    # Still pending
                    break
            else:
                # Order not found, might be filled
                # Get position for this order
                positions = await self.get_positions()
                for pos in positions:
                    if pos.ticket == order_id:
                        # Order is filled
                        return OrderResult(
                            order_id=order_id,
                            symbol=pos.symbol,
                            action=pos.action,
                            volume=pos.volume,
                            price=pos.price_open,
                            sl=pos.sl,
                            tp=pos.tp,
                            comment=pos.comment,
                            status=OrderStatus.FILLED,
                            magic=pos.magic
                        )
                raise OrderError(f"Order {order_id} not found")
        
        try:
            result = await asyncio.wait_for(
                self._order_futures[order_id],
                timeout=timeout
            )
            return result
        except asyncio.TimeoutError:
            raise TimeoutError(f"Order {order_id} did not fill within {timeout}s")
        finally:
            self._order_futures.pop(order_id, None)
    
    # fluxV/live/mt5.py (continued)
# fluxV/live/mt5.py (continued from where we left off)

    async def close_position(self, ticket: int) -> bool:
        """Close a position asynchronously"""
        await self._ensure_connected()
        await self._rate_limiter.acquire()
        
        loop = asyncio.get_event_loop()
        
        # Get position
        positions = await loop.run_in_executor(None, mt5.positions_get, ticket)
        if not positions or len(positions) == 0:
            return False
        
        position = positions[0]
        
        # Determine order type for closing
        close_action = mt5.ORDER_TYPE_SELL if position.type == 0 else mt5.ORDER_TYPE_BUY
        tick = await self._get_current_tick(position.symbol)
        if not tick:
            return False
        
        close_price = tick.bid if position.type == 0 else tick.ask
        
        close_request = {""
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": position.symbol,
            "volume": position.volume,
            "type": close_action,
            "position": ticket,
            "price": close_price,
            "deviation": 20,
            "magic": position.magic,
            "comment": "close"
        }
        
        result = await loop.run_in_executor(None, mt5.order_send, close_request)
        return result.retcode == mt5.TRADE_RETCODE_DONE
    
    async def close_all_positions(self, symbol: Optional[str] = None) -> bool:
        """Close all positions asynchronously"""
        positions = await self.get_positions(symbol)
        if not positions:
            return True
        
        # Use TaskGroup for concurrent closing
        try:
            async with asyncio.TaskGroup() as tg:
                tasks = []
                for pos in positions:
                    task = tg.create_task(self.close_position(pos.ticket))
                    tasks.append(task)
                # All tasks complete
                return all(task.result() for task in tasks)
        except Exception as e:
            logger.error(f"Error closing positions: {e}")
            return False
    
    async def get_positions(self, symbol: Optional[str] = None) -> List[Position]:
        """Get all open positions asynchronously"""
        await self._ensure_connected()
        await self._rate_limiter.acquire()
        
        loop = asyncio.get_event_loop()
        positions = await loop.run_in_executor(
            None, mt5.positions_get, symbol
        ) if symbol else await loop.run_in_executor(None, mt5.positions_get)
        
        if not positions:
            return []
        
        return [
            Position(
                ticket=pos.ticket,
                symbol=pos.symbol,
                action=OrderAction.BUY if pos.type == 0 else OrderAction.SELL,
                volume=pos.volume,
                price_open=pos.price_open,
                price_current=pos.price_current,
                sl=pos.sl,
                tp=pos.tp,
                profit=pos.profit,
                comment=pos.comment,
                magic=pos.magic,
                open_time=datetime.fromtimestamp(pos.time),
                swap=pos.swap,
                commission=pos.commission
            )
            for pos in positions
        ]
    
    async def modify_position(
        self, 
        ticket: int, 
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        trailing_stop: Optional[float] = None
    ) -> bool:
        """Modify stop loss and take profit asynchronously"""
        await self._ensure_connected()
        
        if sl is None and tp is None and trailing_stop is None:
            return True
        
        loop = asyncio.get_event_loop()
        
        # Get position info
        positions = await loop.run_in_executor(None, mt5.positions_get, ticket)
        if not positions or len(positions) == 0:
            return False
        
        position = positions[0]
        
        # Get symbol info for normalization
        symbol_info = await self.get_symbol_info(position.symbol)
        if not symbol_info:
            return False
        
        # Normalize SL and TP
        if sl is not None:
            sl = symbol_info.normalize_price(sl)
        if tp is not None:
            tp = symbol_info.normalize_price(tp)
        
        # If trailing stop, calculate new SL
        if trailing_stop is not None:
            tick = await self._get_current_tick(position.symbol)
            if position.type == 0:  # BUY
                sl = tick.bid - trailing_stop
            else:  # SELL
                sl = tick.ask + trailing_stop
            sl = symbol_info.normalize_price(sl)
        
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "symbol": position.symbol,
            "sl": sl or 0,
            "tp": tp or 0,
        }
        
        result = await loop.run_in_executor(None, mt5.order_send, request)
        return result.retcode == mt5.TRADE_RETCODE_DONE
    
    async def get_pending_orders(self, symbol: Optional[str] = None) -> List[OrderResult]:
        """Get all pending orders asynchronously"""
        await self._ensure_connected()
        await self._rate_limiter.acquire()
        
        loop = asyncio.get_event_loop()
        orders = await loop.run_in_executor(
            None, mt5.orders_get, symbol
        ) if symbol else await loop.run_in_executor(None, mt5.orders_get)
        
        if not orders:
            return []
        
        return [
            OrderResult(
                order_id=order.ticket,
                symbol=order.symbol,
                action=OrderAction.BUY if order.type in [0, 2, 4] else OrderAction.SELL,
                volume=order.volume_initial,
                price=order.price_open,
                sl=order.sl,
                tp=order.tp,
                comment=order.comment,
                status=OrderStatus.PENDING,
                magic=order.magic,
                created_time=datetime.fromtimestamp(order.time_setup),
                remaining_volume=order.volume_initial - order.volume_current
            )
            for order in orders
        ]
    
    async def cancel_order(self, ticket: int) -> bool:
        """Cancel a pending order asynchronously"""
        await self._ensure_connected()
        await self._rate_limiter.acquire()
        
        loop = asyncio.get_event_loop()
        
        request = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": ticket,
        }
        
        result = await loop.run_in_executor(None, mt5.order_send, request)
        
        # Remove from futures if exists
        self._order_futures.pop(ticket, None)
        
        return result.retcode == mt5.TRADE_RETCODE_DONE
    
    async def cancel_all_orders(self, symbol: Optional[str] = None) -> bool:
        """Cancel all pending orders asynchronously"""
        orders = await self.get_pending_orders(symbol)
        if not orders:
            return True
        
        try:
            async with asyncio.TaskGroup() as tg:
                tasks = []
                for order in orders:
                    task = tg.create_task(self.cancel_order(order.order_id))
                    tasks.append(task)
                return all(task.result() for task in tasks)
        except Exception as e:
            logger.error(f"Error cancelling orders: {e}")
            return False
    
    def get_mode(self) -> str:
        """Return the current mode"""
        return self._mode
    
    # Private helper methods
    async def _ensure_connected(self):
        """Raise error if not connected"""
        if not await self.is_connected():
            raise ConnectionError("Not connected to MT5. Call connect() first.")
    
    async def _ensure_symbol_available(self, symbol: str):
        """Ensure symbol is available and select it"""
        info = await self.get_symbol_info(symbol)
        if not info:
            raise SymbolNotFoundError(f"Symbol {symbol} not found")
        
        # Select symbol in market watch if not already selected
        loop = asyncio.get_event_loop()
        selected = await loop.run_in_executor(None, mt5.symbol_select, symbol, True)
        if not selected:
            raise SymbolNotFoundError(f"Could not select symbol {symbol}")
    
    async def _is_market_open(self, symbol: str) -> bool:
        """Check if market is open for trading"""
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, mt5.symbol_info, symbol)
        if not info:
            return False
        return info.trade_mode != mt5.SYMBOL_TRADE_MODE_DISABLED
    
    async def _get_current_tick(self, symbol: str) -> Optional[Tick]:
        """Get current tick for a symbol"""
        loop = asyncio.get_event_loop()
        tick = await loop.run_in_executor(None, mt5.symbol_info_tick, symbol)
        if not tick:
            return None
        
        return Tick(
            time=datetime.fromtimestamp(tick.time),
            bid=tick.bid,
            ask=tick.ask,
            last=tick.last,
            volume=tick.volume,
            flags=tick.flags
        )
    
    def _convert_rates_to_bars(self, rates) -> List[Bar]:
        """Convert MT5 rates to Bar objects"""
        bars = []
        for rate in rates:
            bars.append(Bar(
                time=datetime.fromtimestamp(rate[0]),
                open=rate[1],
                high=rate[2],
                low=rate[3],
                close=rate[4],
                volume=int(rate[5]) if rate[5] else 0,
                tick_volume=int(rate[5]) if len(rate) > 5 else 0,
                spread=int(rate[6]) if len(rate) > 6 else 0,
                real_volume=int(rate[7]) if len(rate) > 7 else 0
            ))
        return bars
    
    def _get_mt5_order_type(self, request: OrderRequest) -> tuple:
        """Convert fluxV order type to MT5 order type"""
        if request.order_type == OrderType.MARKET:
            return (mt5.ORDER_TYPE_BUY if request.action == OrderAction.BUY 
                   else mt5.ORDER_TYPE_SELL, "MARKET")
        elif request.order_type == OrderType.LIMIT:
            return (mt5.ORDER_TYPE_BUY_LIMIT if request.action == OrderAction.BUY 
                   else mt5.ORDER_TYPE_SELL_LIMIT, "LIMIT")
        elif request.order_type == OrderType.STOP:
            return (mt5.ORDER_TYPE_BUY_STOP if request.action == OrderAction.BUY 
                   else mt5.ORDER_TYPE_SELL_STOP, "STOP")
        else:
            raise OrderError(f"Unsupported order type: {request.order_type}")
    
    def _get_order_price(self, request: OrderRequest, tick: Tick) -> float:
        """Get the appropriate price for the order"""
        if request.order_type == OrderType.MARKET:
            return tick.ask if request.action == OrderAction.BUY else tick.bid
        return request.price if request.price else 0