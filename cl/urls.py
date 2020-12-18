from django.conf import settings
from django.conf.urls import include, url
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps import views as sitemaps_views
from django.views.decorators.cache import cache_page
from django.views.generic import RedirectView

from cl.audio.sitemap import AudioSitemap
from cl.opinion_page.sitemap import OpinionSitemap, DocketSitemap
from cl.people_db.sitemap import PersonSitemap
from cl.search.models import SEARCH_TYPES
from cl.simple_pages.sitemap import SimpleSitemap
from cl.simple_pages.views import serve_static_file
from cl.sitemap import cached_sitemap
from cl.visualizations.sitemap import VizSitemap

sitemaps = {
    SEARCH_TYPES.ORAL_ARGUMENT: AudioSitemap,
    SEARCH_TYPES.OPINION: OpinionSitemap,
    SEARCH_TYPES.RECAP: DocketSitemap,
    SEARCH_TYPES.PEOPLE: PersonSitemap,
    "visualizations": VizSitemap,
    "simple": SimpleSitemap,
}

urlpatterns = [
    # Admin docs and site
    url(r"^admin/", admin.site.urls),
    url("", include("cl.audio.urls")),
    url("", include("cl.opinion_page.urls")),
    url("", include("cl.simple_pages.urls")),
    url("", include("cl.users.urls")),
    url("", include("cl.favorites.urls")),
    url("", include("cl.people_db.urls")),
    url("", include("cl.search.urls")),
    url("", include("cl.alerts.urls")),
    url("", include("cl.api.urls")),
    url("", include("cl.donate.urls")),
    url("", include("cl.visualizations.urls")),
    url("", include("cl.stats.urls")),
    # Sitemaps
    url(
        r"^sitemap\.xml$",
        cache_page(60 * 60 * 24 * 14, cache="db_cache")(sitemaps_views.index),
        {"sitemaps": sitemaps, "sitemap_url_name": "sitemaps"},
    ),
    url(
        r"^sitemap-(?P<section>.+)\.xml$",
        cached_sitemap,
        {"sitemaps": sitemaps},
        name="sitemaps",
    ),
    # Redirects
    url(
        r"^privacy/$",
        RedirectView.as_view(url="/terms/#privacy", permanent=True),
    ),
    url(
        r"^removal/$",
        RedirectView.as_view(url="/terms/#removal", permanent=True),
    ),
    # Catch-alls that could conflict with other regexps -- place them last
    #   Serve a static file
    url(
        r"^(?P<file_path>(?:recap)/.+)$",
        serve_static_file,
    ),
] + static("/", document_root=settings.MEDIA_ROOT)
