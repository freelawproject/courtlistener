import hashlib
import logging
from datetime import datetime, timezone

from django.conf import settings
from django.core.cache import caches
from django.core.cache.backends.base import BaseCache
from django.db import transaction
from django.urls import reverse
from django.utils.encoding import force_bytes, iri_to_uri
from django.utils.timezone import now as tz_now
from redis import Redis
from cl.sitemaps_infinite import conf

from cl.lib.redis_utils import get_redis_interface
from cl.sitemaps_infinite.base_sitemap import (
    CacheableList,
    InfinitePaginatorSitemap,
)
from cl.sitemaps_infinite.types import TaskCursorData

logger = logging.getLogger(__name__)

REDIS_DB = "CACHE"
HASH_NAME = "large-sitemaps:cursor"

"""
A TypedDict representing the data stored in the Redis hash for the sitemap cursor.

The `section` key contains the name of the sitemap section, and the `cursor` key contains the cursor value for that section.
"""
cursor_data_default = TaskCursorData(
    {
        "section": None,
        "last_page": 0,
        "has_next": True,
    }
)

short_cache_timeout = 60 * 60 * 24
long_cache_timeout = 60 * 60 * 24 * 180


# Set up a task if repetition period is set in conf
@transaction.atomic
def generate_urls_chunk() -> None:
    """Generate next sitemap chunk."""

    redis_db: Redis = get_redis_interface(REDIS_DB)

    db_cache: BaseCache = caches["db_cache"]

    cursor_data: TaskCursorData = cursor_data_default.copy()

    cursor_data_cached: TaskCursorData = redis_db.hgetall(HASH_NAME)
    if cursor_data_cached:
        cursor_data.update(cursor_data_cached)

    # count the number of files generated, stop when we reach the limit
    num_files: int = 0
    current_page: int = cursor_data.get("last_page")

    # Iterate over the sitemap sections, find the place where we left off, and continue from there
    for section, sitemapClass in conf.SITEMAPS.items():

        if num_files >= conf.FILES_PER_CALL:
            break

        # Get from the cache the cursor value for the sitemap section, processed last time
        cursor_section: str | None = cursor_data.get("section")

        if cursor_section is not None and section != cursor_section:
            # the `section` was already processed before, moving to the next section
            continue

        try:
            sitemapObject: InfinitePaginatorSitemap = sitemapClass()
        except Exception as e:
            logger.error(
                f"Error while loading the sitemap class {sitemapClass.__class__} for section {section}: {e}"
            )
            continue

        prev_cursor: str | None = None

        # Pre-generate sitemap pages
        while True:

            if num_files >= conf.FILES_PER_CALL:
                logger.info(
                    f"Reached the limit of {conf.FILES_PER_CALL} files per call for section: {section} and page: {cursor_data.get('last_page')}."
                )
                break

            if not cursor_data.get("has_next", True):
                logger.info(
                    f"No more URLs to generate for section: {section}, page: {cursor_data.get('last_page')} and cursor: {cursor_data.get('cursor')}."
                )

                # the infinite paginator saves the last page in the current section to its cache
                sitemapObject.paginator.save_num_pages(
                    cursor_data.get("last_page")
                )

                break

            # Make the cache key, @see cl.sitemap.make_cache_key()
            cache_key = make_cache_key(sitemapObject, section, current_page)

            # read the last existing page from the cache
            cached_urls: CacheableList | None = db_cache.get(cache_key)

            # Cursor of the current page
            curr_cursor: str | None = getattr(
                cached_urls, "current_cursor", None
            )

            # Need to regenerate the cache, because previous and current cursors do not match
            force_regenerate: bool = (
                prev_cursor is not None
                and curr_cursor is not None
                and curr_cursor != prev_cursor
            )

            if force_regenerate:
                curr_cursor = prev_cursor

            if (
                not force_regenerate
                and cached_urls is CacheableList
                and (tz_now() - cached_urls.expiration_time).total_seconds()
                > short_cache_timeout
            ):
                # No need to regenerate the cache, because it's a full page, move the cursor to the next page
                current_page += 1

                prev_cursor = cached_urls.next_cursor

                cursor_data.update(
                    {
                        "section": section,
                        "last_page": current_page,
                        "has_next": True,
                    }
                )
            else:
                # either re-read the current page or start from the beginning, if `cursor` is None
                sitemapObject.set_cursor(curr_cursor)

                # Get the next page of URLs by cursor
                urls = sitemapObject.get_urls_by_cursor()

                if not urls or len(urls) == 0:
                    logger.info(
                        f"Empty urls query for section: {section}, page: {cursor_data.get('last_page')} and cursor: {cursor_data.get('cursor')}."
                    )
                    cursor_data["has_next"] = False
                    break

                current_page += 1
                # Generate the sitemap cache for the current page

                if len(urls) == sitemapObject.limit:
                    # Full sitemap. Cache it a long time.
                    cache_timeout = long_cache_timeout
                else:
                    # Partial sitemap. Short cache.
                    cache_timeout = short_cache_timeout

                # Save expiration time in the urls object to check it later
                urls.expiration_time = make_expiration_time(
                    db_cache, cache_timeout
                )

                db_cache.set(cache_key, urls, cache_timeout)

                prev_cursor = sitemapObject.cursor

                cursor_data.update(
                    {
                        "section": section,
                        "last_page": current_page,
                        "has_next": sitemapObject.has_next,
                    }
                )

                num_files += 1

        # save the updated cursor data to the cache
        redis_db.hset(
            HASH_NAME,
            mapping=cursor_data,
        )


def make_cache_key(
    sitemapObject: InfinitePaginatorSitemap, section: str, page: str | int
) -> str:
    """Make a Cache key, trying to match the same key generated in cl.sitemap.make_cache_key()

    Note that the full URL will include the various GET parameters.

    :param request: The HttpRequest from the client
    :param section: The section of the sitemap that is loaded
    :return a key that can be used to cache the request
    scheme = sitemapObject.get_protocol()
    """
    scheme = sitemapObject.get_protocol()
    host = sitemapObject.get_domain()

    uri = f"{scheme}://{host}/{reverse('sitemaps', section=section)}?p={page}"

    url = hashlib.md5(force_bytes(iri_to_uri(uri)))

    return f"sitemap.{section}.{url.hexdigest()}"


def make_expiration_time(cache: BaseCache, timeout: int) -> datetime:
    """Make the expiration time for the cache"""

    timeout = cache.get_backend_timeout(timeout)

    if timeout is None:
        exp = datetime.max
    else:
        tz = timezone.utc if settings.USE_TZ else None
        exp = datetime.fromtimestamp(timeout, tz=tz)
    exp = exp.replace(microsecond=0)

    return exp
