from django.conf import settings
from django.http import HttpResponse
from django.template import loader
from django.utils.encoding import smart_str

from cl.lib import sunburnt
from cl.sitemap import items_per_sitemap


def people_sitemap_maker(request):
    conn = sunburnt.SolrInterface(settings.SOLR_PEOPLE_URL, mode='r')
    page = int(request.GET.get("p", 1))
    start = (page - 1) * items_per_sitemap
    params = {
        'q': '*:*',
        'rows': items_per_sitemap,
        'start': start,
        'fl': ','.join([
            'absolute_url',
            'timestamp',
        ]),
        'sort': 'dob asc',
        'caller': 'people_sitemap_maker',
    }
    results = conn.raw_query(**params).execute()

    # Translate Solr object into something Django's template can use
    urls = []
    for result in results:
        urls.append({
            'location': 'https://www.courtlistener.com%s' % result['absolute_url'],
            'changefreq': 'monthly',
            'lastmod': result['timestamp'],
            'priority': '0.5',
        })

    xml = smart_str(loader.render_to_string('sitemap.xml', {'urlset': urls}))
    response = HttpResponse(xml, content_type='application/xml')
    response['X-Robots-Tag'] = 'noindex, noodp, noarchive, noimageindex'
    return response
