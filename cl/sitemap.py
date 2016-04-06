from django.conf import settings
from django.core.urlresolvers import reverse
from django.http import HttpResponse
from django.template import loader
from django.views.decorators.cache import never_cache
from cl.lib import sunburnt


items_per_sitemap = 250
opinion_solr_params = {
    'q': '*:*',
    'rows': items_per_sitemap,
    'start': 0,
    'fl': ','.join([
        'absolute_url',
        'dateFiled',
        'local_path',
        'citeCount',
        'timestamp',
    ]),
    'sort': 'dateFiled asc',
    'caller': 'opinion_sitemap_maker',
}
index_solr_params = {
    'q': '*:*',
    'rows': '0',  # just need the count
    'start': '0',
    'caller': 'sitemap_index',
}


@never_cache
def index_sitemap_maker(request):
    """Generate a sitemap index page

    Counts the number of cases in the site, divides by `items_per_sitemap` and
    provides links items.
    """
    connection_string_sitemap_path_pairs = (
        (settings.SOLR_OPINION_URL, reverse('opinion_sitemap')),
        (settings.SOLR_AUDIO_URL, reverse('oral_argument_sitemap')),
        (settings.SOLR_PEOPLE_URL, reverse('people_sitemap')),
    )
    sites = []
    for connection_string, path in connection_string_sitemap_path_pairs:
        conn = sunburnt.SolrInterface(connection_string, mode='r')
        search_results_object = conn.raw_query(**index_solr_params).execute()
        count = search_results_object.result.numFound
        num_pages = count / items_per_sitemap + 1
        for i in range(1, num_pages + 1):
            sites.append('https://www.courtlistener.com%s?p=%s' % (path, i))

    # Random additional sitemaps.
    sites.extend([
        'https://www.courtlistener.com%s' % reverse('simple_pages_sitemap'),
        'https://www.courtlistener.com/sitemap-visualizations.xml',
    ])

    xml = loader.render_to_string('sitemap_index.xml', {'sitemaps': sites})

    # These links contain case names, so they should get crawled but not
    # indexed
    response = HttpResponse(xml, content_type='application/xml')
    response['X-Robots-Tag'] = 'noindex, noodp, noarchive, noimageindex'
    return response
