import asyncio
import logging
import time
from collections.abc import Callable
from functools import wraps
from hashlib import md5
from math import ceil
from typing import Any, TypeVar
from urllib.parse import urlparse

from asgiref.sync import iscoroutinefunction, sync_to_async
from django.conf import settings
from django.core.cache import caches
from django.core.cache.backends.base import InvalidCacheBackendError
from django.utils.cache import patch_response_headers

from cl.lib.redis_utils import get_redis_interface

logger = logging.getLogger(__name__)

# In-memory cache for tiered_cache decorator (per-process, fastest tier)
# Data model: {cache_key: (expiry_timestamp, cached_value)}
# - cache_key: string built from function module, name, and arguments
# - expiry_timestamp: float (time.time() + timeout) when the entry expires
# - cached_value: the return value of the decorated function
_memory_cache: dict[str, tuple[float, Any]] = {}

T = TypeVar("T")


def tiered_cache(
    timeout: int,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Tiered caching decorator: memory -> Django cache (Redis) -> function.

    Implements a three-tier caching strategy for optimal performance:
    - Tier 1: In-memory dict (fastest, per-process)
    - Tier 2: Django cache backend (Redis, shared across processes)
    - Tier 3: Execute the wrapped function (slowest, e.g., DB query)

    The memory cache is checked first for speed, then Redis for cross-process
    sharing, and finally the function is called if neither has the value.

    The Redis cache timeout is set to 1 second less than the memory cache to
    prevent a race condition where the memory cache could be refreshed from
    Redis just before Redis expires, giving memory the full timeout again.

    :param timeout: Cache timeout in seconds for the memory tier.
    :return: Decorated function with tiered caching.

    Example:
        @tiered_cache(timeout=300)
        def get_expensive_data(key: str) -> dict:
            return expensive_db_query(key)
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            # Build cache key from function name and arguments
            key_parts = [func.__module__, func.__name__]
            key_parts.extend(str(arg) for arg in args)
            key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
            cache_key = f"tiered:{':'.join(key_parts)}"

            current_time = time.time()

            # Tier 1: Check in-memory cache
            if cache_key in _memory_cache:
                expiry, value = _memory_cache[cache_key]
                if current_time < expiry:
                    return value
                # Expired, remove from memory
                del _memory_cache[cache_key]

            # Tier 2: Check Django cache (Redis)
            redis_cache = caches["default"]
            value = redis_cache.get(cache_key)
            if value is not None:
                # Store in memory cache for faster subsequent access
                _memory_cache[cache_key] = (current_time + timeout, value)
                return value

            # Tier 3: Call the function
            value = func(*args, **kwargs)

            # Store in both caches (Redis gets 1 second less to prevent race)
            redis_cache.set(cache_key, value, timeout - 1)
            _memory_cache[cache_key] = (current_time + timeout, value)

            return value

        return wrapper

    return decorator


def clear_tiered_cache() -> None:
    """Clear both tiers of the tiered cache (memory and Redis).

    Useful for testing or when you need to force a refresh.
    """
    # Clear memory tier
    _memory_cache.clear()
    # Clear Redis tier (all keys with tiered: prefix)
    r = get_redis_interface("CACHE")
    keys = list(r.scan_iter(match=":1:tiered:*"))
    if keys:
        r.delete(*keys)


def retry(
    ExceptionToCheck: type[Exception] | tuple[type[Exception], ...],
    tries: int = 4,
    delay: float = 3,
    backoff: float = 2,
    logger: logging.Logger | None = None,
) -> Callable:
    """Retry calling the decorated function using an exponential backoff.

    https://www.saltycrane.com/blog/2009/11/trying-out-retry-decorator-python/
    original from: https://wiki.python.org/moin/PythonDecoratorLibrary#Retry

    :param ExceptionToCheck: the exception to check. may be a tuple of
    exceptions to check
    :type ExceptionToCheck: Exception or tuple
    :param tries: number of times to try (not retry) before giving up
    :type tries: int
    :param delay: initial delay between retries in seconds
    :type delay: int
    :param backoff: backoff multiplier e.g. value of 2 will double the delay
    each retry
    :type backoff: int
    :param logger: logger to use. If None, print
    :type logger: logging.Logger instance
    """

    def _log_wait(exc: Exception, wait: float) -> None:
        msg = "%s, Retrying in %s seconds..."
        params = (exc, wait)
        if logger:
            logger.warning(msg, *params)
        else:
            print(msg % params)

    def deco_retry(f: Callable) -> Callable:
        if iscoroutinefunction(f):

            @wraps(f)
            async def f_retry(*args, **kwargs):
                mtries, mdelay = tries, delay
                while mtries > 1:
                    try:
                        return await f(*args, **kwargs)
                    except ExceptionToCheck as e:
                        _log_wait(e, mdelay)
                        await asyncio.sleep(mdelay)
                        mtries -= 1
                        mdelay *= backoff
                return await f(*args, **kwargs)

            return f_retry  # true decorator
        else:

            @wraps(f)
            def f_retry(*args, **kwargs):
                mtries, mdelay = tries, delay
                while mtries > 1:
                    try:
                        return f(*args, **kwargs)
                    except ExceptionToCheck as e:
                        _log_wait(e, mdelay)
                        time.sleep(mdelay)
                        mtries -= 1
                        mdelay *= backoff
                return f(*args, **kwargs)

            return f_retry  # true decorator

    return deco_retry


def cache_page_ignore_params(timeout: int, cache_alias: str = "default"):
    """Cache the result of a view while ignoring URL query parameters.
    Ensuring that the cache is consistent for different requests with varying
    query strings.

    WARNING:
    - Do not use this decorator on views that rely on query parameters to
      generate unique content.
    - Do not use this decorator on views that require authentication or
    session-based data, as this will cache content for all users, potentially
    exposing confidential information.

    :param timeout: Cache duration (seconds).
    :param cache_alias: The cache alias to use.
    :return: The decorated view function, caching its response.
    """

    def decorator(view_func):
        @wraps(view_func)
        async def _wrapped_view(request, *args, **kwargs):
            url_path = urlparse(request.build_absolute_uri()).path
            hash_key = md5(url_path.encode("ascii"), usedforsecurity=False)

            is_dev_or_test = settings.DEVELOPMENT or settings.TESTING
            should_use_time_based_prefix = (
                cache_alias == "s3" and not is_dev_or_test
            )
            cache_key = f"custom.views.decorator.cache:{hash_key.hexdigest()}"
            if should_use_time_based_prefix:
                days = int(ceil(timeout / (60 * 60 * 24)))
                cache_key = f"{days}-days:{cache_key}"

            try:
                # If the cache alias is "s3" but we're in DEVELOPMENT or TESTING
                # mode, use the default cache instead of S3. Otherwise, use the
                # cache specified by cache_alias.
                if cache_alias == "s3" and is_dev_or_test:
                    cache = caches["default"]
                else:
                    cache = caches[cache_alias]
            except InvalidCacheBackendError as e:
                logger.error(
                    "Cache alias '%s' not found. Error: %s",
                    cache_alias,
                    str(e),
                )
                raise e

            response = cache.get(cache_key)
            if response is not None:
                return response

            response = await view_func(request, *args, **kwargs)
            await sync_to_async(patch_response_headers)(
                response, cache_timeout=timeout
            )
            if hasattr(response, "render") and callable(response.render):
                # Render the response before caching it.
                # Required for TemplateResponse views.
                response.add_post_render_callback(
                    lambda r: cache.set(cache_key, r, timeout)
                )
            else:
                # Cache non-TemplateResponse responses.
                cache.set(cache_key, response, timeout)

            return response

        return _wrapped_view

    return decorator
