from cl.audio.feeds import (
    AllJurisdictionsPodcast, SearchPodcast, JurisdictionPodcast
)
from cl.audio.views import view_audio_file
from cl.audio.sitemap import oral_argument_sitemap_maker
from django.conf.urls import url


urlpatterns = [
    url(r'^audio/(\d*)/(.*)/$', view_audio_file, name="view_audio_file"),

    # Podcasts
    url(r'^podcast/court/(?P<court>\w{1,15})/$', JurisdictionPodcast()),
    url(r'^podcast/court/all/$', AllJurisdictionsPodcast()),
    url(r'^podcast/(search)/', SearchPodcast()),

    # Sitemap
    url(r'^sitemap-oral-arguments\.xml', oral_argument_sitemap_maker),
]
