from math import ceil

from django.conf import settings
from django.core.cache import caches
from django.core.cache.backends.base import BaseCache
from waffle import switch_is_active


def get_s3_cache(fallback_cache: str = "db_cache") -> BaseCache:
    """Get S3 cache in production, fallback cache in dev/test.

    In production, returns the S3 Express cache backend. In development,
    testing, or when the enable-s3-cache waffle switch is disabled,
    returns the specified fallback cache to avoid requiring S3 access
    for local development or to allow quick rollback if issues arise.

    :param fallback_cache: Cache alias to use in dev/test (default: "db_cache")
    :return: Django cache backend instance
    """
    is_dev_or_test = settings.DEVELOPMENT or settings.TESTING
    if is_dev_or_test or not switch_is_active("enable-s3-cache"):
        return caches[fallback_cache]
    return caches["s3"]


def make_s3_cache_key(base_key: str, timeout_seconds: int | None) -> str:
    """Add time-based prefix to cache key for S3 backend.

    In production, adds a prefix like "7-days:" to help organize cache
    entries by their TTL. When timeout is None, uses "persistent:" prefix
    for cache entries that should never expire. In development/testing,
    returns the key unchanged to maintain compatibility with existing
    cache behavior.

    :param base_key: The base cache key (e.g., "clusters-mlt-es:123")
    :param timeout_seconds: Cache timeout in seconds, or None for persistent
    :return: Cache key with time-based prefix (production) or unchanged (dev/test)
    """
    is_dev_or_test = settings.DEVELOPMENT or settings.TESTING
    if is_dev_or_test or not switch_is_active("enable-s3-cache"):
        return base_key
    if timeout_seconds is None:
        return f"persistent:{base_key}"
    days = int(ceil(timeout_seconds / (60 * 60 * 24)))
    return f"{days}-days:{base_key}"
