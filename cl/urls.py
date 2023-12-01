from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps import views as sitemaps_views
from django.urls import include, path, register_converter
from django.views.decorators.cache import cache_page
from django.views.generic import RedirectView

from cl.audio.sitemap import AudioSitemap, BlockedAudioSitemap
from cl.disclosures.sitemap import DisclosureSitemap
from cl.lib.converters import BlankSlugConverter
from cl.opinion_page.sitemap import (
    BlockedDocketSitemap,
    BlockedOpinionSitemap,
    DocketSitemap,
    OpinionSitemap,
)
from cl.people_db.sitemap import PersonSitemap
from cl.search.models import SEARCH_TYPES
from cl.simple_pages.sitemap import SimpleSitemap
from cl.sitemap import cached_sitemap
from cl.visualizations.sitemap import VizSitemap

register_converter(BlankSlugConverter, "blank-slug")

sitemaps = {
    SEARCH_TYPES.ORAL_ARGUMENT: AudioSitemap,
    SEARCH_TYPES.OPINION: OpinionSitemap,
    SEARCH_TYPES.RECAP: DocketSitemap,
    SEARCH_TYPES.PEOPLE: PersonSitemap,
    "disclosures": DisclosureSitemap,
    "visualizations": VizSitemap,
    "simple": SimpleSitemap,
    "blocked-audio": BlockedAudioSitemap,
    "blocked-dockets": BlockedDocketSitemap,
    "blocked-opinions": BlockedOpinionSitemap,
}

urlpatterns = [
    # Admin docs and site
    path(
        # Redirect admin login to our ratelimited version to reduce surface
        # area and enforce ratelimiting.
        "admin/login/",
        RedirectView.as_view(url="/sign-in/", permanent=False),
    ),
    path("admin/", admin.site.urls),
    # App includes
    path("", include("cl.audio.urls")),
    path("", include("cl.corpus_importer.urls")),
    path("", include("cl.opinion_page.urls")),
    path("", include("cl.simple_pages.urls")),
    path("", include("cl.disclosures.urls")),
    path("", include("cl.users.urls")),
    path("", include("cl.favorites.urls")),
    path("", include("cl.people_db.urls")),
    path("", include("cl.search.urls")),
    path("", include("cl.alerts.urls")),
    path("", include("cl.api.urls")),
    path("", include("cl.donate.urls")),
    path("", include("cl.visualizations.urls")),
    path("", include("cl.stats.urls")),
    # Sitemaps
    path(
        "sitemap.xml",
        cache_page(60 * 60 * 24 * 14, cache="db_cache")(sitemaps_views.index),
        {"sitemaps": sitemaps, "sitemap_url_name": "sitemaps"},
    ),
    path(
        "sitemap-<str:section>.xml",
        cached_sitemap,
        {"sitemaps": sitemaps},
        name="sitemaps",
    ),
    # Redirects
    path(
        "privacy/",
        RedirectView.as_view(url="/terms/#privacy", permanent=True),
    ),
    path(
        "removal/",
        RedirectView.as_view(url="/terms/#removal", permanent=True),
    ),
]

if settings.DEVELOPMENT:
    urlpatterns.append(
        path("__debug__/", include("debug_toolbar.urls")),
    )

urlpatterns += static("/", document_root=settings.MEDIA_ROOT)  # type: ignore
