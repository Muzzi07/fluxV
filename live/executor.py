import asyncio
import MetaTrader5 as mt5
from typing import Optional, Dict, Any
from datetime import datetime

from fluxV.core.models import OrderRequest, OrderResult, OrderStatus
from fluxV.core.types import OrderAction, OrderType
from fluxV.core.exceptions import OrderError, InsufficientBalanceError
from fluxV.utils.rate_limiter import RateLimiter
from fluxV.utils.retry import async_retry


class OrderExecutor:
    """Handles order execution with async support"""
    
    def __init__(self, rate_limit: float = 10):
        self._rate_limiter = RateLimiter(rate=rate_limit, per=1.0)
        self._pending_futures: Dict[int, asyncio.Future] = {}
    
    @async_retry(max_attempts=3, delay=0.1)
    async def execute_order(self, request: OrderRequest) -> OrderResult:
        """Execute an order"""
        await self._rate_limiter.acquire()
        
        loop = asyncio.get_event_loop()
        
        # Get symbol info
        symbol_info = await loop.run_in_executor(None, mt5.symbol_info, request.symbol)
        if not symbol_info:
            raise OrderError(f"Symbol {request.symbol} not found")
        
        # Get current tick
        tick = await loop.run_in_executor(None, mt5.symbol_info_tick, request.symbol)
        if not tick:
            raise OrderError(f"Cannot get tick for {request.symbol}")
        
        # Build MT5 request
        mt5_request = self._build_mt5_request(request, symbol_info, tick)
        
        # Send order
        result = await loop.run_in_executor(None, mt5.order_send, mt5_request)
        
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
            volume=request.volume,
            price=result.price,
            sl=request.sl,
            tp=request.tp,
            comment=request.comment,
            status=OrderStatus.FILLED if request.order_type == OrderType.MARKET else OrderStatus.PENDING,
            magic=request.magic,
            message=result.comment
        )
        
        # If pending, create future for monitoring
        if request.order_type != OrderType.MARKET:
            self._pending_futures[result.order] = asyncio.get_event_loop().create_future()
        
        return order_result
    
    def _build_mt5_request(self, request, symbol_info, tick) -> Dict:
        """Build MT5 order request"""
        # Determine order type
        if request.order_type == OrderType.MARKET:
            order_type = mt5.ORDER_TYPE_BUY if request.action == OrderAction.BUY else mt5.ORDER_TYPE_SELL
            action = mt5.TRADE_ACTION_DEAL
            price = tick.ask if request.action == OrderAction.BUY else tick.bid
        else:
            order_type = self._get_pending_order_type(request)
            action = mt5.TRADE_ACTION_PENDING
            price = request.price
        
        # Normalize SL and TP
        sl = round(request.sl, symbol_info.digits) if request.sl else 0
        tp = round(request.tp, symbol_info.digits) if request.tp else 0
        
        return {
            "action": action,
            "symbol": request.symbol,
            "volume": request.volume,
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
    
    def _get_pending_order_type(self, request) -> int:
        """Get MT5 pending order type"""
        if request.action == OrderAction.BUY:
            if request.order_type == OrderType.LIMIT:
                return mt5.ORDER_TYPE_BUY_LIMIT
            elif request.order_type == OrderType.STOP:
                return mt5.ORDER_TYPE_BUY_STOP
        else:
            if request.order_type == OrderType.LIMIT:
                return mt5.ORDER_TYPE_SELL_LIMIT
            elif request.order_type == OrderType.STOP:
                return mt5.ORDER_TYPE_SELL_STOP
        raise OrderError(f"Unsupported order type: {request.order_type}")