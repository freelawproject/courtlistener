from django.conf import settings
from django.core.urlresolvers import reverse
from django.http import HttpResponse
from django.template import loader
from django.utils.encoding import smart_str
from django.views.decorators.cache import cache_page

from cl.lib.scorched_utils import ExtraSolrInterface
from cl.lib.search_utils import build_court_count_query

items_per_sitemap = 10000


def make_sitemap_solr_params(sort, caller):
    params = {
        'q': '*',
        'rows': items_per_sitemap,
        'start': 0,
        'fl': ','.join([
            # Not all indexes have all these fields, but it causes no errors.
            'absolute_url',
            'docket_absolute_url',
            'local_path',
            'timestamp',
        ]),
        'sort': sort,
        'caller': caller,
    }
    if caller == 'r_sitemap':
        params.update({
            # Use groups so we only get one result per docket,
            # not one per document.
            'group': 'true',
            'group.ngroups': 'true',
            'group.field': 'docket_id',
            # Smaller groups for performance
            'group.limit': 1,
        })
    return params


def normalize_grouping(result):
    """If a grouped result item, normalize it to look like a regular one.

    If a regular result, do nothing.
    """
    if result.get('doclist') is not None:
        # Grouped result, normalize it.
        return result['doclist']['docs'][0]
    else:
        return result


def make_solr_sitemap(request, solr_url, params, changefreq, low_priority_pages,
                      url_field):
    solr = ExtraSolrInterface(solr_url)
    page = int(request.GET.get('p', 1))
    params['start'] = (page - 1) * items_per_sitemap
    results = solr.query().add_extra(**params).execute()

    urls = []
    cl = 'https://www.courtlistener.com'
    for result in results:
        result = normalize_grouping(result)
        url_strs = ['%s%s' % (cl, result[url_field])]
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


@cache_page(60 * 60 * 24 * 7, cache='db_cache')  # One week
def index_sitemap_maker(request):
    """Generate a sitemap index page

    Counts the number of cases in the site, divides by `items_per_sitemap` and
    provides links items.
    """
    connection_string_sitemap_path_pairs = (
        (settings.SOLR_OPINION_URL, reverse('opinion_sitemap'), False),
        (settings.SOLR_RECAP_URL, reverse('recap_sitemap'), True),
        (settings.SOLR_AUDIO_URL, reverse('oral_argument_sitemap'), False),
        (settings.SOLR_PEOPLE_URL, reverse('people_sitemap'), False),
    )
    sites = []
    for connection_string, path, group in connection_string_sitemap_path_pairs:
        conn = ExtraSolrInterface(connection_string)
        response = conn.query().add_extra(**build_court_count_query(group)).count()
        court_count_tuples = response.facet_counts.facet_fields['court_exact']
        for court, count in court_count_tuples:
            num_pages = count / items_per_sitemap + 1
            for page in range(1, num_pages + 1):
                sites.append('https://www.courtlistener.com%s?p=%s&court=%s' %
                             (path, page, court))

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
