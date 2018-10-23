from django.conf.urls import url
from django.views.generic import RedirectView

from cl.simple_pages.sitemap import sitemap_maker
from cl.simple_pages.views import (
    about, advanced_search, browser_warning, contact, contact_thanks,
    contribute, coverage_graph, donation_help, faq, feeds, humans,
    latest_terms,
    alert_help, markdown_help, old_terms, podcasts, robots, tools_page,
    validate_for_bing, validate_for_google, validate_for_google2,
    validate_for_wot,
)

urlpatterns = [
    # Footer stuff
    url(r'^about/$', about, name='about'),
    url(r'^faq/$', faq, name="faq"),
    url(r'^coverage/$', coverage_graph, name='coverage'),
    url(r'^feeds/$', feeds, name='feeds_info'),
    url(r'^podcasts/$', podcasts, name='podcasts'),
    url(r'^contribute/$', contribute, name='contribute'),
    url(r'^contact/$', contact, name="contact"),
    url(r'^contact/thanks/$', contact_thanks, name='contact_thanks'),

    # Help pages
    url(r'^help/markdown/$', markdown_help, name="markdown_help"),
    url(r'^help/alerts/$', alert_help, name="alert_help"),
    url(r'^help/donations/$', donation_help, name="donation_help"),
    url(r'^help/search-operators/$', advanced_search, name="advanced_search"),

    # Added 2018-10-23
    url(r'^search/advanced-techniques/$',
        RedirectView.as_view(pattern_name='advanced_search', permanent=True)),

    url(r'^terms/v/(\d{1,2})/$', old_terms, name='old_terms'),
    url(r'^terms/$', latest_terms, name='terms'),

    # Randoms
    url(
        r'^tools/$',
        tools_page,
        name='tools',
    ),
    url(
        r'^bad-browser/$',
        browser_warning,
        name='bad_browser',
    ),

    # Robots & Humans
    url(
        r'^robots\.txt$',
        robots,
        name='robots'
    ),
    url(
        r'^humans\.txt$',
        humans,
        name='humans',
    ),

    # Sitemap:
    url(
        r'^sitemap-simple-pages\.xml$',
        sitemap_maker,
        name='simple_pages_sitemap',
    ),

    # SEO-related stuff
    url(r'^BingSiteAuth.xml$', validate_for_bing),
    url(r'^googleef3d845637ccb353.html$', validate_for_google),
    url(r'^google646349975c2495b6.html$', validate_for_google2),
    url(r'^mywot8f5568174e171ff0acff.html$', validate_for_wot),

    # Favicon, touch icons, etc.
    url(r'^favicon\.ico$',
        RedirectView.as_view(
            url='/static/ico/favicon.ico',
            permanent=True)),
    url(r'^touch-icon-192x192\.png',
        RedirectView.as_view(
            url='/static/png/touch-icon-192x192.png',
            permanent=True)),
    url(r'^apple-touch-icon\.png$',
        RedirectView.as_view(
            url='/static/png/apple-touch-icon.png',
            permanent=True)),
    url(r'^apple-touch-icon-72x72-precomposed\.png$',
        RedirectView.as_view(
            url='/static/png/apple-touch-icon-72x72-precomposed.png',
            permanent=True)),
    url(r'^apple-touch-icon-76x76-precomposed\.png$',
        RedirectView.as_view(
            url='/static/png/apple-touch-icon-76x76-precomposed.png',
            permanent=True)),
    url(r'^apple-touch-icon-114x114-precomposed\.png$',
        RedirectView.as_view(
            url='/static/png/apple-touch-icon-114x114-precomposed.png',
            permanent=True)),
    url(r'^apple-touch-icon-120x120-precomposed\.png$',
        RedirectView.as_view(
            url='/static/png/apple-touch-icon-120x120-precomposed.png',
            permanent=True)),
    url(r'^apple-touch-icon-144x144-precomposed\.png$',
        RedirectView.as_view(
            url='/static/png/apple-touch-icon-144x144-precomposed.png',
            permanent=True)),
    url(r'^apple-touch-icon-152x152-precomposed\.png$',
        RedirectView.as_view(
            url='/static/png/apple-touch-icon-152x152-precomposed.png',
            permanent=True)),
    url(r'^apple-touch-icon-180x180-precomposed\.png$',
        RedirectView.as_view(
            url='/static/png/apple-touch-icon-180x180-precomposed.png',
            permanent=True)),
    url(r'^apple-touch-icon-precomposed\.png$',
        RedirectView.as_view(
            url='/static/png/apple-touch-icon-precomposed.png',
            permanent=True)),
]
