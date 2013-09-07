from alert.lib import sunburnt
from django.conf import settings
from django.contrib.flatpages.models import FlatPage
from django.http import HttpResponse
from django.template import loader
from django.utils.encoding import smart_str
from django.views.decorators.cache import never_cache


@never_cache
def sitemap_maker(request, size=250):
    """Generate a sitemap index page

    Counts the number of cases in the site, divides by 1,000 and provides links
    for all of them.
    """
    protocol = request.is_secure() and 'https' or 'http'

    conn = sunburnt.SolrInterface(settings.SOLR_URL, mode='r')
    params = {'q': '*:*'}
    page = request.GET.get("p", False)
    if page:
        # Page was found, so serve that page.
        params['rows'] = size
        params['start'] = (int(page) - 1) * size
        params['fl'] = 'absolute_url,dateFiled,local_path,citeCount'
        params['sort'] = 'dateFiled asc'
        search_results_object = conn.raw_query(**params).execute()

        # Translate Solr object into something Django's template can use
        urls = []
        for result in search_results_object:
            url = {}
            url_strs = ['%s://www.courtlistener.com%s' % (protocol, result['absolute_url'])]
            if int(result['citeCount']) > 0:
                # Only include this page if there are citations.
                url_strs.append('%s://www.courtlistener.com%scited-by/' % (protocol, result['absolute_url']))
            try:
                url_strs.append('%s://www.courtlistener.com/%s' % (protocol, result['local_path']))
            except KeyError:
                # No local_path key.
                pass

            for url_str in url_strs:
                url['location'] = url_str
                url['changefreq'] = 'never'
                if any(str in url_str for str in ['cited-by', 'pdf', 'doc', 'wpd']):
                    url['priority'] = '0.4'
                else:
                    url['priority'] = '0.5'
                urls.append(dict(url))

        xml = smart_str(loader.render_to_string('sitemap.xml', {'urlset': urls}))

    else:
        # If no page number, thus the index page.
        params['rows'] = '0'  # just need the count
        params['start'] = '0'
        search_results_object = conn.raw_query(**params).execute()
        count = search_results_object.result.numFound

        i = 0
        sites = ['%s://www.courtlistener.com/sitemap-flat.xml' % protocol]
        # For flat pages
        while i < count:
            sites.append('%s://www.courtlistener.com/sitemap.xml?p=%s' % (protocol, i / size + 1))
            i += size

        xml = loader.render_to_string('sitemap_index.xml', {'sitemaps': sites})

    # These links contain case names, so they should get crawled but not indexed
    response = HttpResponse(xml, mimetype='application/xml')
    response['X-Robots-Tag'] = 'noindex, noodp, noarchive, noimageindex'
    return response


@never_cache
def flat_sitemap_maker(request):
    """
    Generate a sitemap for the flatpagess.
    """
    def priority(page):
        """Could be a dictionary or something too..."""
        if 'about' in str(page.get_absolute_url).lower():
            return 0.6
        elif 'coverage' in str(page.get_absolute_url).lower():
            return 0.7
        elif 'contribute' in str(page.get_absolute_url).lower():
            return 0.7
        else:
            return 0.2

    flat_pages = FlatPage.objects.all()
    urls = []
    for page in flat_pages:
        url = {'location': 'https://www.courtlistener.com%s' % page.get_absolute_url(),
               'changefreq': 'monthly',
               'priority': priority(page)}
        urls.append(url)

    # Add a few non-flat pages
    urls.append([{'location': 'https://www.courtlistener.com/dump-info/',
                  'changefreq': 'monthly',
                  'priority': '0.7'},
                 {'location': 'https://www.courtlistener.com/api/jurisdictions/',
                  'changefreq': 'monthly',
                  'priority': '0.5'}])

    xml = smart_str(loader.render_to_string('sitemap.xml', {'urlset': urls}))
    return HttpResponse(xml, mimetype='application/xml')
