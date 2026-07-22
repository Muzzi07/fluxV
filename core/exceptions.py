"""
Custom exceptions for fluxV
"""

class fluxVError(Exception):
    """Base exception for fluxV library"""
    pass

class ConnectionError(fluxVError):
    """Raised when connection to MT5 fails"""
    pass

class OrderError(fluxVError):
    """Raised when order placement fails"""
    pass

class DataError(fluxVError):
    """Raised when data retrieval fails"""
    pass

class SymbolNotFoundError(fluxVError):
    """Raised when a symbol is not found"""
    pass

class InsufficientBalanceError(fluxVError):
    """Raised when account has insufficient balance"""
    pass

class InvalidOrderError(fluxVError):
    """Raised when order parameters are invalid"""
    pass

class MarketClosedError(fluxVError):
    """Raised when market is closed for a symbol"""
    pass

class TimeoutError(fluxVError):
    """Raised when an operation times out"""
    pass

class SlippageError(fluxVError):
    """Raised when order experiences excessive slippage"""
    pass