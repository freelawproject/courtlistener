from django.conf import settings

from cl.sitemap import make_sitemap_solr_params, make_solr_sitemap


def people_sitemap_maker(request):
    return make_solr_sitemap(
        request,
        settings.SOLR_PEOPLE_URL,
        make_sitemap_solr_params('dob asc,name_reverse asc',
                                 'p_sitemap'),
        'monthly',
        [],
        'absolute_url',
    )
