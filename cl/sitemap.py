from django.conf import settings
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
    connection_string_obj_type_pairs = (
        (settings.SOLR_OPINION_URL, 'opinions'),
        (settings.SOLR_AUDIO_URL, 'oral-arguments'),
    )
    sites = []
    for connection_string, obj_type in connection_string_obj_type_pairs:
        conn = sunburnt.SolrInterface(connection_string, mode='r')
        search_results_object = conn.raw_query(**index_solr_params).execute()
        count = search_results_object.result.numFound
        num_pages = count / items_per_sitemap + 1
        for i in range(1, num_pages + 1):
            sites.append(
                'https://www.courtlistener.com/sitemap-%s.xml?p=%s' % (obj_type, i)
            )

    # Random additional sitemaps.
    sites.extend([
        'https://www.courtlistener.com/sitemap-simple-pages.xml',
        'https://www.courtlistener.com/sitemap-visualizations.xml',
    ])

    xml = loader.render_to_string('sitemap_index.xml', {'sitemaps': sites})

    # These links contain case names, so they should get crawled but not
    # indexed
    response = HttpResponse(xml, content_type='application/xml')
    response['X-Robots-Tag'] = 'noindex, noodp, noarchive, noimageindex'
    return response
