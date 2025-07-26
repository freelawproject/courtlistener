from collections import OrderedDict

from django.contrib.sitemaps import views as sitemaps_views
from django.urls import path
from django.views.decorators.cache import cache_page

from cl.opinion_page.sitemap import DocketSitemap
from cl.search.models import SEARCH_TYPES
from cl.sitemap import cached_sitemap

# List the models that should use pregenerated sitemaps
pregenerated_sitemaps = OrderedDict(
    {
        SEARCH_TYPES.RECAP: DocketSitemap,
    }
)

# use shorter cache time for sitemap index
urlpatterns = [
    path(
        "large-sitemap.xml",
        cache_page(60 * 60 * 24, cache="db_cache")(sitemaps_views.index),
        {
            "sitemaps": pregenerated_sitemaps,
            "sitemap_url_name": "sitemaps-pregenerated",
        },
    ),
    path(
        "large-sitemap-<str:section>.xml",
        cached_sitemap,
        {"sitemaps": pregenerated_sitemaps},
        name="sitemaps-pregenerated",
    ),
]
