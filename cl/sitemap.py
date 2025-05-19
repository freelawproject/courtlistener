import hashlib
from calendar import timegm
from datetime import datetime

from django.contrib.sitemaps import Sitemap
from django.contrib.sitemaps.views import x_robots_tag
from django.contrib.sites.shortcuts import get_current_site
from django.core.cache import caches
from django.core.paginator import EmptyPage, InvalidPage, PageNotAnInteger
from django.http import Http404, HttpRequest, HttpResponse
from django.template.response import TemplateResponse
from django.utils.encoding import escape_uri_path, force_bytes
from django.utils.http import http_date

from cl.lib.ratelimiter import ratelimiter_all_2_per_m


def make_cache_key(
    request: HttpRequest, section: str, force_page: bool = False
) -> str:
    """Make a Cache key for a URL

    This is a simplified version of django's get_cache_key method, which
    factors in additional things like the method and the headers that were
    received, but it adds a section parameter to make the key slightly more
    readable.

    Note that only 'p' GET parameter is included in the key.

    :param request: The HttpRequest from the client
    :param section: The section of the sitemap that is loaded
    :param force_page: Include page=1 to the cache key by default
    :return a key that can be used to cache the request
    """
    # url without query string
    base_url: str = request.build_absolute_uri(escape_uri_path(request.path))

    # include only 'p' parameter to the cache key, make it more deterministic
    if page := request.GET.get("p", 1 if force_page else None):
        base_url = f"{base_url}?p={page}"

    url = hashlib.md5(force_bytes(base_url))

    return f"sitemap.{section}.{url.hexdigest()}"


@ratelimiter_all_2_per_m
@x_robots_tag
def cached_sitemap(
    request: HttpRequest,
    sitemaps: dict[str, Sitemap],
    section: str | None = None,
    template_name: str = "sitemap.xml",
    content_type: str = "application/xml",
) -> HttpResponse:
    """Copy the django sitemap code, but cache URLs

    See Django documentation for parameter details.
    """

    req_protocol = request.scheme
    req_site = get_current_site(request)

    if section not in sitemaps:
        raise Http404(f"No sitemap available for section: {section!r}")
    sitemap = sitemaps[section]
    page = request.GET.get("p", 1)

    # handle infinite sitemaps, force p=1 by default
    force_page = bool(getattr(sitemap, "force_page_in_cache", False))

    cache = caches["db_cache"]
    cache_key = make_cache_key(request, section, force_page)
    urls = cache.get(cache_key)

    # return HttpResponse(f'{request.build_absolute_uri(escape_uri_path(request.path))} {cache_key} {urls}', content_type='text/plain')
    if not urls and not isinstance(urls, list):
        # No cache for this page, otherwise cache exists and it could be the empty list
        try:
            if callable(sitemap):
                sitemap = sitemap()
            urls = sitemap.get_urls(
                page=page, site=req_site, protocol=req_protocol
            )
        except EmptyPage:
            raise Http404(f"Page {page} empty")
        except PageNotAnInteger:
            raise Http404(f"No page '{page}'")
        except InvalidPage:
            raise Http404(f"Page '{page}' does not exist")

        if len(urls) == sitemap.limit:
            # Full sitemap. Cache it a long time.
            cache_length = 60 * 60 * 24 * 180
        else:
            # Partial sitemap. Short cache.
            cache_length = 60 * 60 * 24
        cache.set(cache_key, urls, cache_length)

    lastmod = None
    all_sites_lastmod = True
    if all_sites_lastmod:
        site_lastmod = getattr(sitemap, "latest_lastmod", None)
        if site_lastmod is not None:
            site_lastmod = (
                site_lastmod.utctimetuple()
                if isinstance(site_lastmod, datetime)
                else site_lastmod.timetuple()
            )
            lastmod = (
                site_lastmod if lastmod is None else max(lastmod, site_lastmod)
            )
        else:
            all_sites_lastmod = False

    response = TemplateResponse(
        request, template_name, {"urlset": urls}, content_type=content_type
    )
    if all_sites_lastmod and lastmod is not None:
        # if lastmod is defined for all sites, set header so as
        # ConditionalGetMiddleware is able to send 304 NOT MODIFIED
        response["Last-Modified"] = http_date(timegm(lastmod))
    return response
