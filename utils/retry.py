import asyncio
import logging
from functools import wraps
from typing import Type, Tuple, Optional, Callable, Union

logger = logging.getLogger(__name__)


def async_retry(
    max_attempts: int = 3,
    delay: float = 0.5,
    backoff: float = 2.0,
    exceptions: Union[Type[Exception], Tuple[Type[Exception], ...]] = Exception,
    on_retry_callback: Optional[Callable] = None
):
    """
    Async retry decorator with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts
        delay: Initial delay between retries (seconds)
        backoff: Multiplier for exponential backoff
        exceptions: Exception(s) to catch and retry on
        on_retry_callback: Optional callback called before each retry
                            (signature: func(attempt, exception))

    Returns:
        Decorated async function with retry logic

    Examples:
        >>> @async_retry(max_attempts=5, delay=1.0, exceptions=(ConnectionError,))
        >>> async def connect():
        ...     # Try connecting
        ...     pass
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == max_attempts:
                        logger.error(
                            f"All {max_attempts} attempts failed for "
                            f"{func.__name__}: {e}"
                        )
                        raise

                    wait_time = delay * (backoff ** (attempt - 1))

                    logger.warning(
                        f"Attempt {attempt}/{max_attempts} failed for "
                        f"{func.__name__}: {e}. Retrying in {wait_time:.2f}s..."
                    )

                    if on_retry_callback:
                        on_retry_callback(attempt, e)

                    await asyncio.sleep(wait_time)

            # Should not reach here, but just in case
            if last_exception:
                raise last_exception

        return wrapper
    return decorator
