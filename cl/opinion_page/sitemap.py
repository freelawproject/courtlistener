from django.conf import settings

from cl.sitemap import make_sitemap_solr_params, make_solr_sitemap


def opinion_sitemap_maker(request):
    return make_solr_sitemap(
        request,
        settings.SOLR_OPINION_URL,
        make_sitemap_solr_params('dateFiled asc', 'o_sitemap'),
        'monthly',
        ['pdf', 'doc', 'wpd'],
        'absolute_url',
    )


def recap_sitemap_maker(request):
    return make_solr_sitemap(
        request,
        settings.SOLR_RECAP_URL,
        make_sitemap_solr_params('dateFiled asc', 'r_sitemap'),
        'weekly',
        [],
        'docket_absolute_url',
    )
