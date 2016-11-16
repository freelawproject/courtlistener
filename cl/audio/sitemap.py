from django.conf import settings

from cl.sitemap import make_solr_sitemap, make_sitemap_solr_params


def oral_argument_sitemap_maker(request):
    return make_solr_sitemap(
        request,
        settings.SOLR_AUDIO_URL,
        make_sitemap_solr_params('dateArgued asc',
                                 'oa_sitemap'),
        'yearly',
        ['mp3'],
    )
