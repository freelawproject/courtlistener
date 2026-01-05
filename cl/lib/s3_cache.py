from math import ceil

from django.conf import settings
from django.core.cache import caches


def get_s3_cache(fallback_cache: str = "db_cache"):
    """Get S3 cache in production, fallback cache in dev/test.

    In production, returns the S3 Express cache backend. In development
    or testing environments, returns the specified fallback cache to avoid
    requiring S3 access for local development.

    :param fallback_cache: Cache alias to use in dev/test (default: "db_cache")
    :return: Django cache backend instance
    """
    is_dev_or_test = settings.DEVELOPMENT or settings.TESTING
    if is_dev_or_test:
        return caches[fallback_cache]
    return caches["s3"]


def make_s3_cache_key(base_key: str, timeout_seconds: int) -> str:
    """Add time-based prefix to cache key for S3 backend.

    In production, adds a prefix like "7-days:" to help organize cache
    entries by their TTL. In development/testing, returns the key unchanged
    to maintain compatibility with existing cache behavior.

    :param base_key: The base cache key (e.g., "clusters-mlt-es:123")
    :param timeout_seconds: Cache timeout in seconds
    :return: Cache key with time-based prefix (production) or unchanged (dev/test)
    """
    is_dev_or_test = settings.DEVELOPMENT or settings.TESTING
    if is_dev_or_test:
        return base_key
    days = int(ceil(timeout_seconds / (60 * 60 * 24)))
    return f"{days}-days:{base_key}"
