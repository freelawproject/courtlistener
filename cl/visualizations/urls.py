from django.urls import path

from cl.visualizations.views import (
    VisualizationDeprecationRedirectView,
    view_embedded_visualization,
)

urlpatterns = [
    # Redirects for deprecated pages
    path(
        "visualizations/scotus-mapper/",
        VisualizationDeprecationRedirectView.as_view(),
        name="mapper_homepage",
    ),
    path(
        "visualizations/scotus-mapper/new/",
        VisualizationDeprecationRedirectView.as_view(),
        name="new_visualization",
    ),
    path(
        "visualizations/scotus-mapper/<int:pk>/edit/",
        VisualizationDeprecationRedirectView.as_view(),
        name="edit_visualization",
    ),
    path(
        "visualizations/scotus-mapper/<int:pk>/<blank-slug:slug>/",
        VisualizationDeprecationRedirectView.as_view(),
        name="view_visualization",
    ),
    path(
        "visualizations/gallery/",
        VisualizationDeprecationRedirectView.as_view(),
        name="viz_gallery",
    ),
    # Keep embed functionality
    path(
        "visualizations/scotus-mapper/<int:pk>/embed/",
        view_embedded_visualization,
        name="view_embedded_visualization",
    ),
]
