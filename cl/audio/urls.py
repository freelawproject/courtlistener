from django.urls import path, re_path

from cl.audio.feeds import (
    AllJurisdictionsPodcast,
    JurisdictionPodcast,
    SearchPodcast,
)
from cl.audio.views import view_audio_file

urlpatterns = [
    path(
        "audio/<int:pk>/<blank-slug:_>/",
        view_audio_file,  # type: ignore[arg-type]
        name="view_audio_file",
    ),
    # Podcasts
    path(
        "podcast/court/all/",
        AllJurisdictionsPodcast(),
        name="all_jurisdictions_podcast",
    ),
    path(
        "podcast/court/<str:court>/",
        JurisdictionPodcast(),
        name="jurisdiction_podcast",
    ),
    re_path(r"^podcast/(search)/", SearchPodcast(), name="search_podcast"),
]
