from django.core.urlresolvers import reverse
from django.http import HttpResponse
from django.template import loader
from django.utils.encoding import smart_str


def make_url_dict(view_name, changefreq='yearly', priority=0.5):
    return {
        'location': 'https://www.courtlistener.com%s' % reverse(view_name),
        'changefreq': changefreq,
        'priority': priority,
    }


def sitemap_maker(request):
    urls = [
        # API
        make_url_dict('api_index', priority=0.7),
        make_url_dict('rest_docs', priority=0.6),
        make_url_dict('bulk_data_index', priority=0.6),

        # Donation
        make_url_dict('donate', priority=0.7),

        # Simple pages
        make_url_dict('about', priority=0.6),
        make_url_dict('faq', priority=0.6),
        make_url_dict('coverage', priority=0.4),
        make_url_dict('feeds_info', priority=0.4, changefreq='never'),
        make_url_dict('contribute', priority=0.6, changefreq='never'),
        make_url_dict('contact', priority=0.5),
        make_url_dict('markdown_help', priority=0.4, changefreq='never'),
        make_url_dict('advanced_search', priority=0.5),
        make_url_dict('terms', priority=0.1),

        # Users
        make_url_dict('sign-in', priority=0.6, changefreq='never'),
        make_url_dict('register', priority=0.6, changefreq='never'),
        make_url_dict('password_reset', priority=0.4, changefreq='never'),

        # Visualizations
        make_url_dict('mapper_homepage', priority=0.7),
        make_url_dict('new_visualization', priority=0.4),
        make_url_dict('viz_gallery', priority=0.6, changefreq='hourly'),
    ]

    xml = smart_str(loader.render_to_string('sitemap.xml', {'urlset': urls}))
    return HttpResponse(xml, content_type='application/xml')
