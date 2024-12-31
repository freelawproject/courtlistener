from datetime import datetime
from functools import cached_property
from typing import Any, Tuple, Union

from cursor_pagination import CursorPaginator
from django.conf import settings
from django.contrib import sitemaps
from django.contrib.sites.models import Site
from django.contrib.sites.requests import RequestSite
from django.core.paginator import InvalidPage
from redis import Redis

from cl.lib.redis_utils import get_redis_interface
from cl.sitemaps_infinite.types import SitemapsPagesNumber

REDIS_DB = "CACHE"
HASH_NAME = "large-sitemaps:num_pages"


class CacheableList(list):
    """
    A wrapper around a list that can hold the additional attributes,
    used to store the cache metadata - e.g. the `expiration_time` and `cursor` used to get that list.

    Used to keep the compatibility with the old cached sitemap generation
    and to avoid the sync problems, if cache metadata is handled in a separate cache key.

    There is no way to get the cache item expiration time using Django cache API.
    """

    expiration_time: datetime
    current_cursor: str
    next_cursor: str


class CustomCursorPaginator(CursorPaginator):
    """
    A custom CursorPaginator that uses the number of pages from the cache.
    """

    section: str | None = None

    def __init__(self, queryset, ordering: dict[str], section: str):
        super().__init__(queryset, ordering)
        self.section = section

    @cached_property
    def num_pages(self) -> int:
        """
        Returns the total number of pages in the paginator, reads it from the cache.
        Overloaded version to be compatible with the standard Django Paginator API.
        """
        redis_db: Redis = get_redis_interface(REDIS_DB)
        num_pages_cached: SitemapsPagesNumber = redis_db.hgetall(HASH_NAME)

        if self.section is None:
            raise Exception("The section is not set in the paginator.")

        return num_pages_cached.get(self.section, 1)

    def save_num_pages(self, num: int) -> None:
        """
        Saves the number of pages for the current section to the cache.
        """
        redis_db: Redis = get_redis_interface(REDIS_DB)
        redis_db.hset(HASH_NAME, self.section, num)


class InfinitePaginatorSitemap(sitemaps.Sitemap):
    """
    A base class for the sitemap that uses seek pagination from CursorPaginator to generate a large number of URLs.

    This sitemap is intended to be pre-generated by a Command rather than generated on-the-fly,
    as accessing it directly will raise an `InvalidPage` exception.

    The `get_urls_by_cursor` method is used to generate the URLs,
    taking an optional cursor parameter to fetch the next set of URLs.
    """

    _cursor: Union[str, None, False] = False
    _has_next: bool = False

    @property
    def section(self) -> str:
        """
        The section of the response that this cursor data applies to, as a string or bytes.
        """
        raise Exception(
            "The section property should by provided by the subclass."
        )

    def set_cursor(self, cursor: str | None = None):
        self._cursor = cursor

    @property
    def cursor(self):
        return self._cursor

    @property
    def has_next(self):
        return self._has_next

    @property
    def ordering(self) -> Tuple[str]:
        """
        Ordering property should be provided by the subclass and will be used in the paginator.
        """
        raise Exception("The ordering should by provided by the subclass.")

    @property
    def paginator(self):
        return CustomCursorPaginator(
            self._items(), self.ordering, self.section
        )

    def get_urls(
        self,
        page=1,
        site=None,
        protocol=None,
    ) -> list[dict[str, Any]]:
        """
        Raises an `InvalidPage` exception when this sitemap is accessed directly,
        as it is intended to be pre-generated by a Command rather than generated on-the-fly.
        """
        raise InvalidPage(
            "This sitemap uses 'seek pagination' and should be pregenerated by running the command: `generate_sitemaps`."
        )

    def get_urls_by_cursor(
        self,
        site: Site | RequestSite | None = None,
        protocol: str | None = None,
    ) -> CacheableList[dict[str, Any]]:
        """
        Generates a list of URLs for the sitemap, using a cursor to fetch the next set of URLs.

        Args:
            cursor (int | str, optional): An optional cursor value to fetch the next set of URLs.
            site (sitemaps.Site | sitemaps.RequestSite | None, optional): The site object to use for generating the URLs.
            protocol (str | None, optional): The protocol to use for generating the URLs.

        Returns:
            list[dict[str, Any]]: A list of dictionaries representing the URLs for the sitemap.
        """
        if self._cursor == False:
            raise Exception(
                "The cursor should be set (by calling `set_cursor`) before calling `get_urls_by_cursor` method."
            )

        protocol = self.get_protocol(protocol)
        domain = self.get_domain(site)

        urls, self._cursor, self._has_next = self._urls(
            self._cursor, protocol, domain
        )

        return urls

    def _urls(
        self, cursor: str, protocol: str, domain: str
    ) -> Tuple[CacheableList[dict[str, Any]], str, bool]:

        urls = CacheableList()
        # keep the `current_cursor` with the list as cached metadata, can be used later to re-fetch the list
        urls.current_cursor = cursor

        latest_lastmod = None
        all_items_lastmod = True  # track if all items have a lastmod

        paginator_page = self.paginator.page(first=self.limit, after=cursor)

        for item in paginator_page:
            loc = f"{protocol}://{domain}{self._location(item)}"
            priority = self._get("priority", item)
            lastmod = self._get("lastmod", item)

            if all_items_lastmod:
                all_items_lastmod = lastmod is not None
                if all_items_lastmod and (
                    latest_lastmod is None or lastmod > latest_lastmod
                ):
                    latest_lastmod = lastmod

            url_info = {
                "item": item,
                "location": loc,
                "lastmod": lastmod,
                "changefreq": self._get("changefreq", item),
                "priority": str(priority if priority is not None else ""),
                "alternates": [],
            }

            if self.i18n and self.alternates:
                item_languages = self.get_languages_for_item(item[0])
                for lang_code in item_languages:
                    loc = f"{protocol}://{domain}{self._location(item, lang_code)}"
                    url_info["alternates"].append(
                        {
                            "location": loc,
                            "lang_code": lang_code,
                        }
                    )
                if self.x_default and settings.LANGUAGE_CODE in item_languages:
                    lang_code = settings.LANGUAGE_CODE
                    loc = f"{protocol}://{domain}{self._location(item, lang_code)}"
                    loc = loc.replace(f"/{lang_code}/", "/", 1)
                    url_info["alternates"].append(
                        {
                            "location": loc,
                            "lang_code": "x-default",
                        }
                    )

            urls.append(url_info)

        if all_items_lastmod and latest_lastmod:
            self.latest_lastmod = latest_lastmod

        next_cursor = (
            self.paginator.cursor(paginator_page[-1])
            if len(paginator_page)
            else None
        )

        # Save `next_cursor` in the list as cached metadata
        urls.next_cursor = next_cursor

        return (
            urls,
            next_cursor,
            paginator_page.has_next,
        )
