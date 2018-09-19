from django.conf import settings
from django.views.decorators.cache import cache_page

from cl.sitemap import make_sitemap_solr_params, make_solr_sitemap


@cache_page(60 * 60 * 24 * 14, cache='db_cache')  # two weeks
def opinion_sitemap_maker(request):
    return make_solr_sitemap(
        request,
        settings.SOLR_OPINION_URL,
        make_sitemap_solr_params('dateFiled asc', 'o_sitemap'),
        'monthly',
        ['pdf', 'doc', 'wpd'],
        'absolute_url',
    )


@cache_page(60 * 60 * 24 * 14, cache='db_cache')  # two weeks
def recap_sitemap_maker(request):
    return make_solr_sitemap(
        request,
        settings.SOLR_RECAP_URL,
        make_sitemap_solr_params('docket_id asc', 'r_sitemap'),
        'weekly',
        [],
        'docket_absolute_url',
    )
