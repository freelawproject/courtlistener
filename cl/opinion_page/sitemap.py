from django.conf import settings
from django.http import HttpResponse
from django.template import loader
from django.utils.encoding import smart_str

from cl.lib import sunburnt
from cl.sitemap import items_per_sitemap


def opinion_sitemap_maker(request):
    conn = sunburnt.SolrInterface(settings.SOLR_OPINION_URL, mode='r')
    page = request.GET.get("p")
    start = (int(page) - 1) * items_per_sitemap
    params = {
        'q': '*:*',
        'rows': items_per_sitemap,
        'start': start,
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
    search_results_object = conn.raw_query(**params).execute()

    # Translate Solr object into something Django's template can use
    urls = []
    for result in search_results_object:
        url_strs = [
            'https://www.courtlistener.com%s' % result['absolute_url']]
        if int(result['citeCount']) > 0:
            # Only include this page if there are citations.
            url_strs.append(
                'https://www.courtlistener.com%scited-by/' % result['absolute_url'])
        url_strs.append(
            'https://www.courtlistener.com%sauthorities/' % result['absolute_url']
        )
        if result.get('local_path') and result.get('local_path') != '':
            url_strs.append(
                'https://www.courtlistener.com/%s' % result['local_path'])

        sitemap_item = {}
        for url_str in url_strs:
            sitemap_item['location'] = url_str
            sitemap_item['changefreq'] = 'yearly'
            sitemap_item['lastmod'] = result['timestamp']
            if any(s in url_str for s in
                   ['authorities', 'cited-by', 'pdf', 'doc', 'wpd']):
                sitemap_item['priority'] = '0.3'
            else:
                sitemap_item['priority'] = '0.5'
            urls.append(dict(sitemap_item))

    xml = smart_str(loader.render_to_string('sitemap.xml', {'urlset': urls}))
    # These links contain case names, so they should get crawled but not
    # indexed
    response = HttpResponse(xml, content_type='application/xml')
    response['X-Robots-Tag'] = 'noindex, noodp, noarchive, noimageindex'
    return response
