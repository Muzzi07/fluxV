"""
Rate limiter for async operations
"""
import asyncio
import time
from collections import deque
from typing import Optional


class RateLimiter:
    """
    Rate limiter for controlling the frequency of operations.
    """
    
    def __init__(self, rate: float = 10, per: float = 1.0):
        """
        Initialize rate limiter.
        
        Args:
            rate: Maximum number of operations per time period
            per: Time period in seconds
        """
        self._rate = rate
        self._per = per
        self._tokens = deque(maxlen=int(rate))
        self._lock = asyncio.Lock()
    
    async def acquire(self) -> bool:
        """
        Acquire a token for rate-limited operation.
        Returns True when it's safe to proceed.
        """
        async with self._lock:
            now = time.time()
            
            # Remove expired tokens
            while self._tokens and now - self._tokens[0] > self._per:
                self._tokens.popleft()
            
            # Check if we can acquire
            if len(self._tokens) < self._rate:
                self._tokens.append(now)
                return True
            
            # Wait for next token
            wait_time = self._per - (now - self._tokens[0]) + 0.01
            await asyncio.sleep(max(0, wait_time))
            
            # Try again recursively
            return await self.acquire()
    
    def reset(self):
        """Reset the rate limiter"""
        self._tokens.clear()