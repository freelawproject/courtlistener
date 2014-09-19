from django.conf.urls import patterns
from django.views.generic import RedirectView
from alert.simple_pages.views import tools_page, validate_for_google, \
    validate_for_google2, validate_for_wot, validate_for_bing, robots, \
    advanced_search, contact_thanks, contact, feeds, coverage_graph, faq, about, \
    browser_warning


urlpatterns = patterns('',
    # Footer stuff
    (r'^about/$', about),
    (r'^faq/$', faq),
    (r'^coverage/$', coverage_graph),
    (r'^feeds/$', feeds),
    (r'^contact/$', contact),
    (r'^contact/thanks/$', contact_thanks),

    # Advanced search page
    (r'^search/advanced-techniques/$', advanced_search),

    # Robots
    (r'^robots.txt$', robots),

    # Randoms
    (r'^tools/$', tools_page),
    (r'^bad-browser/$', browser_warning),

    # SEO-related stuff
    (r'^BingSiteAuth.xml$', validate_for_bing),
    (r'^googleef3d845637ccb353.html$', validate_for_google),
    (r'^google646349975c2495b6.html$', validate_for_google2),
    (r'^mywot8f5568174e171ff0acff.html$', validate_for_wot),

    # Favicon, touch icons, etc.
    (r'^favicon\.ico$',
     RedirectView.as_view(url='/static/ico/favicon.ico', permanent=True)),
    (r'^apple-touch-icon\.png$',
     RedirectView.as_view(url='/static/png/apple-touch-icon.png',
                          permanent=True)),
    (r'^apple-touch-icon-57x57-precomposed\.png$',
     RedirectView.as_view(
         url='/static/png/apple-touch-icon-57x57-precomposed.png',
         permanent=True)),
    (r'^apple-touch-icon-72x72-precomposed\.png$',
     RedirectView.as_view(
         url='/static/png/apple-touch-icon-72x72-precomposed.png',
         permanent=True)),
    (r'^apple-touch-icon-114x114-precomposed\.png$',
     RedirectView.as_view(
         url='/static/png/apple-touch-icon-114x114-precomposed.png',
         permanent=True)),
    (r'^apple-touch-icon-precomposed\.png$',
     RedirectView.as_view(url='/static/png/apple-touch-icon-precomposed.png',
                          permanent=True)),
)


