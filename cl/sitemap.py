from django.conf import settings
from django.core.urlresolvers import reverse
from django.http import HttpResponse
from django.template import loader
from django.utils.encoding import smart_str
from django.views.decorators.cache import never_cache

from cl.lib import sunburnt
from cl.lib.scorched_utils import ExtraSolrInterface

items_per_sitemap = 250

index_solr_params = {
    'q': '*',
    'rows': '0',  # just need the count
    'start': '0',
    'caller': 'sitemap_index',
}


def make_sitemap_solr_params(sort, caller):
    return {
        'q': '*',
        'rows': items_per_sitemap,
        'start': 0,
        'fl': ','.join([
            'absolute_url',
            # Not all indexes have this field, but it causes no errors.
            'local_path',
            'timestamp',
        ]),
        'sort': sort,
        'caller': caller,
    }


def make_solr_sitemap(request, solr_url, params, changefreq,
                      low_priority_pages):
    solr = ExtraSolrInterface(solr_url)
    page = int(request.GET.get('p', 1))
    params['start'] = (page - 1) * items_per_sitemap
    results = solr.query().add_extra(**params).execute()

    urls = []
    cl = 'https://www.courtlistener.com'
    for result in results:
        url_strs = ['%s%s' % (cl, result['absolute_url'])]
        if result.get('local_path') and \
                not result['local_path'].endswith('.xml'):
            url_strs.append('%s/%s' % (cl, result['local_path']))

        item = {}
        for url_str in url_strs:
            item['location'] = url_str
            item['changefreq'] = changefreq
            item['lastmod'] = result['timestamp']
            if any(s in url_str for s in low_priority_pages):
                item['priority'] = '0.3'
            else:
                item['priority'] = '0.5'
            urls.append(item.copy())

    xml = smart_str(loader.render_to_string('sitemap.xml', {'urlset': urls}))
    response = HttpResponse(xml, content_type='application/xml')
    response['X-Robots-Tag'] = 'noindex, noodp, noarchive, noimageindex'
    return response


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
