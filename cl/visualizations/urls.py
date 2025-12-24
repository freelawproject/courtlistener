from django.urls import path, re_path

from cl.visualizations.views import (
    VisualizationDeprecationRedirectView,
    view_embedded_visualization,
)

urlpatterns = [
    # Embed functionality (must be before catch-all)
    path(
        "visualizations/scotus-mapper/<int:pk>/embed/",
        view_embedded_visualization,
        name="view_embedded_visualization",
    ),
    # Catch-all redirects all other visualization paths to API docs
    re_path(
        r"^visualizations/.*$",
        VisualizationDeprecationRedirectView.as_view(),
    ),
]
