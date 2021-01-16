from django.conf.urls import url
from django.contrib.sitemaps.views import sitemap

from cl.visualizations.sitemap import VizSitemap
from cl.visualizations.views import (
    delete_visualization,
    edit_visualization,
    gallery,
    mapper_homepage,
    new_visualization,
    privatize_visualization,
    restore_visualization,
    share_visualization,
    view_embedded_visualization,
    view_visualization,
)

urlpatterns = [
    url(
        r"^visualizations/scotus-mapper/$",
        mapper_homepage,
        name="mapper_homepage",
    ),
    url(
        r"^visualizations/scotus-mapper/new/$",
        new_visualization,
        name="new_visualization",
    ),
    url(
        r"^visualizations/scotus-mapper/(?P<pk>\d*)/edit/$",
        edit_visualization,
        name="edit_visualization",
    ),
    url(
        # Check JS files if changing this config.
        r"^visualizations/scotus-mapper/delete/$",
        delete_visualization,
        name="delete_visualization",
    ),
    url(
        r"^visualizations/scotus-mapper/restore/",
        restore_visualization,
        name="restore_visualization",
    ),
    url(
        r"^visualizations/scotus-mapper/share/",
        share_visualization,
        name="share_visualization",
    ),
    url(
        r"^visualizations/scotus-mapper/privatize/",
        privatize_visualization,
        name="privatize_visualization",
    ),
    url(
        r"^visualizations/scotus-mapper/(?P<pk>\d*)/embed/$",
        view_embedded_visualization,
        name="view_embedded_visualization",
    ),
    url(
        r"^visualizations/scotus-mapper/(?P<pk>\d*)/(?P<slug>[^/]*)/$",
        view_visualization,
        name="view_visualization",
    ),
    url(r"^visualizations/gallery/$", gallery, name="viz_gallery"),
]
