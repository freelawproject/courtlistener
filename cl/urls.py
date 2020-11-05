from django.conf import settings
from django.conf.urls import include, url
from django.conf.urls.static import static
from django.contrib import admin
from django.views.generic import RedirectView
from cl.sitemap import index_sitemap_maker
from cl.simple_pages.views import serve_static_file

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
    url(r"^sitemap\.xml$", index_sitemap_maker),
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
