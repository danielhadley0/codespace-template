"""
Retry utilities with exponential backoff.
"""
import asyncio
import functools
from typing import Callable, TypeVar, Any
import structlog

from config.settings import settings

logger = structlog.get_logger()

T = TypeVar('T')


def retry_with_backoff(
    max_retries: int = None,
    base_delay: int = None,
    exceptions: tuple = (Exception,)
):
    """
    Decorator for retrying async functions with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Base delay in seconds for exponential backoff
        exceptions: Tuple of exceptions to catch and retry

    Usage:
        @retry_with_backoff(max_retries=3)
        async def my_function():
            ...
    """
    if max_retries is None:
        max_retries = settings.max_retry_attempts
    if base_delay is None:
        base_delay = settings.retry_backoff_base

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt < max_retries:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(
                            "Function call failed, retrying",
                            function=func.__name__,
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            delay=delay,
                            error=str(e)
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            "Function call failed after all retries",
                            function=func.__name__,
                            max_retries=max_retries,
                            error=str(e)
                        )

            # Raise the last exception if all retries failed
            if last_exception:
                raise last_exception

        return wrapper
    return decorator


async def retry_with_timeout(
    func: Callable,
    timeout: float,
    *args,
    **kwargs
) -> Any:
    """
    Execute an async function with a timeout.

    Args:
        func: Async function to execute
        timeout: Timeout in seconds
        *args: Positional arguments for func
        **kwargs: Keyword arguments for func

    Returns:
        Result of func or raises asyncio.TimeoutError

    Raises:
        asyncio.TimeoutError: If function doesn't complete within timeout
    """
    try:
        return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
    except asyncio.TimeoutError:
        logger.error(
            "Function timed out",
            function=func.__name__,
            timeout=timeout
        )
        raise
