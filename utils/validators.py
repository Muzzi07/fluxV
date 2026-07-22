from typing import Optional, Tuple
from fluxV.core.exceptions import InvalidOrderError


def validate_symbol(symbol: str) -> bool:
    """Validate trading symbol"""
    if not symbol or not isinstance(symbol, str):
        raise InvalidOrderError("Symbol must be a non-empty string")
    return True


def validate_volume(volume: float) -> bool:
    """Validate trading volume"""
    if volume <= 0:
        raise InvalidOrderError("Volume must be positive")
    return True


def validate_sl_tp(
    sl: Optional[float],
    tp: Optional[float],
    price: float,
    action: str
) -> Tuple[Optional[float], Optional[float]]:
    """Validate and normalize SL and TP"""
    if sl is not None:
        if action == "BUY" and sl >= price:
            raise InvalidOrderError("Stop loss must be below entry price for BUY")
        if action == "SELL" and sl <= price:
            raise InvalidOrderError("Stop loss must be above entry price for SELL")
    
    if tp is not None:
        if action == "BUY" and tp <= price:
            raise InvalidOrderError("Take profit must be above entry price for BUY")
        if action == "SELL" and tp >= price:
            raise InvalidOrderError("Take profit must be below entry price for SELL")
    
    if sl is not None and tp is not None:
        if action == "BUY" and sl >= tp:
            raise InvalidOrderError("SL must be below TP for BUY")
        if action == "SELL" and sl <= tp:
            raise InvalidOrderError("SL must be above TP for SELL")
    
    return sl, tp