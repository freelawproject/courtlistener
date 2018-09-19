from django.conf import settings
from django.views.decorators.cache import cache_page

from cl.sitemap import make_solr_sitemap, make_sitemap_solr_params


@cache_page(60 * 60 * 24 * 14, cache='db_cache')  # two weeks
def oral_argument_sitemap_maker(request):
    return make_solr_sitemap(
        request,
        settings.SOLR_AUDIO_URL,
        make_sitemap_solr_params('dateArgued asc',
                                 'oa_sitemap'),
        'monthly',
        ['mp3'],
        'absolute_url',
    )
