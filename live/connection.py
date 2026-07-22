import asyncio
import MetaTrader5 as mt5
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager

from fluxV.core.exceptions import ConnectionError
from fluxV.utils.logging import AsyncLogger

logger = AsyncLogger(__name__)


class ConnectionManager:
    """Manages MT5 connection lifecycle"""
    
    def __init__(self):
        self._connected = False
        self._connection_params: Dict[str, Any] = {}
        self._lock = asyncio.Lock()
    
    async def connect(
        self,
        login: Optional[int] = None,
        password: Optional[str] = None,
        server: Optional[str] = None,
        path: Optional[str] = None
    ) -> bool:
        """Connect to MT5 terminal"""
        async with self._lock:
            loop = asyncio.get_event_loop()
            
            # Initialize MT5
            initialized = await loop.run_in_executor(None, mt5.initialize, path)
            if not initialized:
                raise ConnectionError(f"Failed to initialize MT5: {mt5.last_error()}")
            
            # Login if credentials provided
            if login and password and server:
                authorized = await loop.run_in_executor(
                    None, mt5.login, login, password, server
                )
                if not authorized:
                    await self._shutdown()
                    raise ConnectionError(f"Failed to login: {mt5.last_error()}")
            
            self._connected = True
            self._connection_params = {
                'login': login,
                'server': server,
                'path': path
            }
            
            await logger.info(f"Connected to MT5 terminal")
            return True
    
    async def disconnect(self) -> bool:
        """Disconnect from MT5 terminal"""
        async with self._lock:
            if self._connected:
                await self._shutdown()
            return True
    
    async def _shutdown(self):
        """Shutdown MT5 connection"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, mt5.shutdown)
        self._connected = False
        await logger.info("Disconnected from MT5")
    
    async def is_connected(self) -> bool:
        """Check if connected"""
        if not self._connected:
            return False
        try:
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, mt5.terminal_info)
            return info is not None
        except Exception:
            return False
    
    @asynccontextmanager
    async def connection_context(self, **kwargs):
        """Context manager for connection"""
        try:
            await self.connect(**kwargs)
            yield self
        finally:
            await self.disconnect()