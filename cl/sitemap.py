import hashlib
from calendar import timegm
from datetime import datetime
from typing import Dict, Optional

from django.contrib.sitemaps import Sitemap
from django.contrib.sitemaps.views import x_robots_tag
from django.contrib.sites.shortcuts import get_current_site
from django.core.cache import caches
from django.core.paginator import EmptyPage, PageNotAnInteger
from django.http import Http404, HttpRequest, HttpResponse
from django.template.response import TemplateResponse
from django.utils.encoding import force_bytes, iri_to_uri
from django.utils.http import http_date

from cl.lib.ratelimiter import ratelimiter_all_2_per_m


def make_cache_key(request: HttpRequest, section: str) -> str:
    """Make a Cache key for a URL

    This is a simplified version of django's get_cache_key method, which
    factors in additional things like the method and the headers that were
    received, but it adds a section parameter to make the key slightly more
    readable.

    Note that the full URL will include the various GET parameters.

    :param request: The HttpRequest from the client
    :param section: The section of the sitemap that is loaded
    :return a key that can be used to cache the request
    """
    url = hashlib.md5(force_bytes(iri_to_uri(request.build_absolute_uri())))
    return f"sitemap.{section}.{url.hexdigest()}"


@ratelimiter_all_2_per_m
@x_robots_tag
def cached_sitemap(
    request: HttpRequest,
    sitemaps: Dict[str, Sitemap],
    section: Optional[str] = None,
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
    site = sitemaps[section]
    page = request.GET.get("p", 1)

    cache = caches["db_cache"]
    cache_key = make_cache_key(request, section)
    urls = cache.get(cache_key, [])
    if not urls:
        try:
            if callable(site):
                site = site()
            urls = site.get_urls(
                page=page, site=req_site, protocol=req_protocol
            )
        except EmptyPage:
            raise Http404(f"Page {page} empty")
        except PageNotAnInteger:
            raise Http404(f"No page '{page}'")

        if len(urls) == site.limit:
            # Full sitemap. Cache it a long time.
            cache_length = 60 * 60 * 24 * 180
        else:
            # Partial sitemap. Short cache.
            cache_length = 60 * 60 * 24
        cache.set(cache_key, urls, cache_length)

    lastmod = None
    all_sites_lastmod = True
    if all_sites_lastmod:
        site_lastmod = getattr(site, "latest_lastmod", None)
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
