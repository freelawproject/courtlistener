import logging
import time
from functools import wraps
from hashlib import md5
from typing import Callable, Tuple, Type, Union
from urllib.parse import urlparse

from asgiref.sync import sync_to_async
from django.core.cache import cache
from django.utils.cache import patch_response_headers

logger = logging.getLogger(__name__)


def retry(
    ExceptionToCheck: Union[Type[Exception], Tuple[Type[Exception], ...]],
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

    def deco_retry(f: Callable) -> Callable:
        @wraps(f)
        def f_retry(*args, **kwargs):
            mtries, mdelay = tries, delay
            while mtries > 1:
                try:
                    return f(*args, **kwargs)
                except ExceptionToCheck as e:
                    msg = "%s, Retrying in %d seconds..." % (str(e), mdelay)
                    if logger:
                        logger.warning(msg)
                    else:
                        print(msg)
                    time.sleep(mdelay)
                    mtries -= 1
                    mdelay *= backoff
            return f(*args, **kwargs)

        return f_retry  # true decorator

    return deco_retry


def cache_page_ignore_params(timeout: int):
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
    :return: The decorated view function, caching its response.
    """

    def decorator(view_func):
        @wraps(view_func)
        async def _wrapped_view(request, *args, **kwargs):
            url_path = urlparse(request.build_absolute_uri()).path
            hash_key = md5(url_path.encode("ascii"), usedforsecurity=False)
            cache_key = f"custom.views.decorator.cache:{hash_key.hexdigest()}"
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
