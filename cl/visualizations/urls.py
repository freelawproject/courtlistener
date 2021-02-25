from django.urls import path

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
    path(
        "visualizations/scotus-mapper/",
        mapper_homepage,
        name="mapper_homepage",
    ),
    path(
        "visualizations/scotus-mapper/new/",
        new_visualization,
        name="new_visualization",
    ),
    path(
        "visualizations/scotus-mapper/<int:pk>/edit/",
        edit_visualization,
        name="edit_visualization",
    ),
    path(
        # Check JS files if changing this config.
        "visualizations/scotus-mapper/delete/",
        delete_visualization,
        name="delete_visualization",
    ),
    path(
        "visualizations/scotus-mapper/restore/",
        restore_visualization,
        name="restore_visualization",
    ),
    path(
        "visualizations/scotus-mapper/share/",
        share_visualization,
        name="share_visualization",
    ),
    path(
        "visualizations/scotus-mapper/privatize/",
        privatize_visualization,
        name="privatize_visualization",
    ),
    path(
        "visualizations/scotus-mapper/<int:pk>/embed/",
        view_embedded_visualization,
        name="view_embedded_visualization",
    ),
    path(
        "visualizations/scotus-mapper/<int:pk>/<blank-slug:slug>/",
        view_visualization,
        name="view_visualization",
    ),
    path("visualizations/gallery/", gallery, name="viz_gallery"),
]
