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

from cl.lib.redis_utils import get_redis_interface
from cl.sitemaps_infinite import conf
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
        "has_next": 1,
    }
)

short_cache_timeout = 60 * 60 * 24
long_cache_timeout = 60 * 60 * 24 * 180


# Set up a task if repetition period is set in conf
@transaction.atomic
def generate_urls_chunk(force_regenerate: bool = False) -> None:
    """Generates the next chunk of URLs for the sitemap. This function is responsible for managing the sitemap generation process, including caching, cursor handling, and limiting the number of files generated per call.

    The function iterates over the configured sitemap sections, loading the appropriate `InfinitePaginatorSitemap` class for each section. It then generates the sitemap pages for each section, caching the results and updating the cursor data in Redis. The function stops generating new pages once the configured limit of files per call has been reached.

    The function uses the `make_cache_key()` and `make_expiration_time()` helper functions to generate the cache keys and expiration times for the sitemap pages. It also handles cases where the cached cursor data does not match the current cursor, indicating that the sitemap data may have changed and needs to be regenerated.
    """

    redis_db: Redis = get_redis_interface(REDIS_DB)

    db_cache: BaseCache = caches["db_cache"]

    cursor_data: TaskCursorData = cursor_data_default.copy()

    cursor_data_cached: TaskCursorData = redis_db.hgetall(HASH_NAME)
    if cursor_data_cached:
        cursor_data.update(cursor_data_cached)

    # Make sure the cursor data is in the correct format
    # TODO: use serializer to store the cursor data in redis keeping the proper field types
    cursor_data.update(
        {
            "last_page": int(cursor_data.get("last_page")),
            "has_next": int(cursor_data.get("has_next")),
        }
    )

    # count the number of files generated, stop when we reach the limit
    num_files: int = 0
    current_page: int = cursor_data.get("last_page")
    forced_exit = False

    # Iterate over the sitemap sections, find the place where we left off, and continue from there
    for section, sitemapClass in conf.SITEMAPS.items():

        # Get from the cache the cursor value for the sitemap section, processed last time
        cursor_section: str | None = cursor_data.get("section")

        if cursor_section is not None and section != cursor_section:
            # the `section` was already processed before, moving to the next section
            continue

        try:
            sitemapObject: InfinitePaginatorSitemap = sitemapClass()
            logger.info(
                f"Loaded the sitemap class '{sitemapClass.__name__}' for section {section}."
            )
        except Exception as e:
            logger.error(
                f"Error while loading the sitemap class '{sitemapClass.__name__}' for section {section}: {e}"
            )
            continue

        current_cursor: str | None = None

        # Pre-generate sitemap pages in the current section
        while True:

            if num_files >= conf.FILES_PER_CALL:
                logger.info(
                    f"Reached the limit of {conf.FILES_PER_CALL} files per call for section: {section} and page: {cursor_data.get('last_page')}."
                )

                forced_exit = True
                break

            # Make the cache key, @see cl.sitemap.make_cache_key()
            cache_key = make_cache_key(sitemapObject, section, current_page)

            # read the last existing page from the cache
            cached_urls: CacheableList | None = db_cache.get(cache_key)

            if (
                current_cursor is None
                and cached_urls is None
                and current_page > 1
            ):
                # reset the section page number to 1 and regenerate the whole section
                current_page = 1
                continue

            # Cursor of the current page read from the cache
            cached_cursor: str | None = getattr(
                cached_urls, "current_cursor", None
            )

            logger.info(
                f"Cursor of the current page read from the cache: {cached_cursor}, passed from the previous iteration: {current_cursor}, current_page: {current_page}"
            )

            # Need to regenerate the cache, because cached and currently processed cursors do not match
            # probably, the items inside the previous page were deleted or the whole section is just started
            force_regenerate: bool = force_regenerate or (
                current_cursor is not None
                and cached_cursor is not None
                and cached_cursor != current_cursor
            )

            if (
                not force_regenerate
                and hasattr(
                    cached_urls, "expiration_time"
                )  # cached_urls is CacheableList
                and (cached_urls.expiration_time - tz_now()).total_seconds()
                > short_cache_timeout
            ):
                logger.info(
                    f"No need to regenerate the cache '{cache_key}' for the page {current_page}, because it's a full page, move the cursor to the next page"
                )

                # No need to regenerate the cache, because it's a full page, move the cursor to the next page
                current_page += 1

                current_cursor = cached_urls.next_cursor

                cursor_data.update(
                    {
                        "section": section,
                        "last_page": current_page,
                        "has_next": 1,
                    }
                )
            else:
                current_cursor = current_cursor or cached_cursor

                logger.info(
                    f"(Re)generating the cache '{cache_key}' for the page {current_page}, because the previous and current cursors do not match"
                )

                # either re-read the current page or start from the beginning, if `cursor` is None
                sitemapObject.set_cursor(current_cursor)

                # Get the next page of URLs by cursor
                urls = sitemapObject.get_urls_by_cursor()

                if not urls or len(urls) == 0:
                    logger.info(
                        f"Empty urls query for section: {section}, page: {current_page} and cursor: {cursor_data.get('cursor')}."
                    )
                    cursor_data["has_next"] = 0
                    continue

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

                # Save the sitemap page data to the cache
                db_cache.set(cache_key, urls, cache_timeout)

                logger.info(
                    f"Generated sitemap cache for section: {section}, page: {current_page} and cursor: {current_cursor}."
                )

                cursor_data.update(
                    {
                        "section": section,
                        "last_page": current_page,
                        "has_next": int(sitemapObject.has_next),
                    }
                )

                if not sitemapObject.has_next:
                    logger.info(
                        f"No more URLs to generate for section: {section}, page: {current_page} and cursor: {current_cursor}."
                    )

                    # the infinite paginator saves the last page in the current section to its cache
                    sitemapObject.paginator.save_num_pages(current_page)

                    current_cursor = None

                    break

                # Move the cursor to the next page
                current_cursor = sitemapObject.cursor
                current_page += 1

                num_files += 1

        # save the updated cursor data to the cache
        redis_db.hset(
            HASH_NAME,
            mapping=cursor_data,
        )

    if not forced_exit:
        # All sections are generated, resetting the cursor data to restart generation for all sitemaps sections on next run
        reset_sitemaps_cursor()
        logger.info(
            "Resetting the cursor data to restart generation for all sitemaps sections"
        )


def reset_sitemaps_cursor() -> None:
    """Reset the cursor data for all sitemaps sections"""
    redis_db: Redis = get_redis_interface(REDIS_DB)
    redis_db.delete(HASH_NAME)


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

    uri = f"{scheme}://{host}{reverse('sitemaps-pregenerated', kwargs={"section": section})}?p={page}"
    url = hashlib.md5(force_bytes(iri_to_uri(uri)))

    return f"sitemap.{section}.{url.hexdigest()}"


def make_expiration_time(cache: BaseCache, timeout: int) -> datetime:
    """Make the expiration time for the cache"""

    timeout = cache.get_backend_timeout(timeout)  # timestamp in future

    if timeout is None:
        exp = datetime.max
    else:
        tz = timezone.utc if settings.USE_TZ else None
        exp = datetime.fromtimestamp(timeout, tz=tz)
    exp = exp.replace(microsecond=0)

    return exp
