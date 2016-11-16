from django.conf import settings

from cl.sitemap import make_sitemap_solr_params, make_solr_sitemap


def opinion_sitemap_maker(request):
    return make_solr_sitemap(
        request,
        settings.SOLR_OPINION_URL,
        make_sitemap_solr_params('dateFiled asc', 'o_sitemap'),
        'yearly',
        ['pdf', 'doc', 'wpd'],
    )
