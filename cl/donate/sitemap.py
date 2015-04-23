from django.http import HttpResponse
from django.template import loader
from django.utils.encoding import smart_str


def donate_sitemap_maker(request):
    urls = [
        {
            'location': 'https://www.courtlistener.com/donate/',
            'changefreq': 'yearly',
            'priority': 0.7,
        }
    ]

    xml = smart_str(loader.render_to_string('sitemap.xml', {'urlset': urls}))
    return HttpResponse(xml, mimetype='application/xml')
