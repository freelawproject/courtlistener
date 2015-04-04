from alert.audio.feeds import AllJurisdictionsPodcast, SearchPodcast, \
    JurisdictionPodcast
from alert.audio.views import view_audio_file
from alert.audio.sitemap import oral_argument_sitemap_maker
from alert.urls import pacer_codes
from django.conf.urls import patterns, url



urlpatterns = patterns('',
    url(r'^audio/(\d*)/(.*)/$', view_audio_file, name="view_audio_file"),

    # Podcasts
    (r'^podcast/court/(?P<court>' + '|'.join(pacer_codes) + ')/$',
     JurisdictionPodcast()),
    (r'^podcast/court/all/$', AllJurisdictionsPodcast()),
    (r'^podcast/(search)/', SearchPodcast()),

    # Sitemap
    (r'^sitemap-oral-arguments\.xml', oral_argument_sitemap_maker),
)
