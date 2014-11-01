from django.conf.urls import patterns
from django.views.generic import RedirectView
from alert.simple_pages.views import tools_page, validate_for_google, \
    validate_for_google2, validate_for_wot, validate_for_bing, robots, \
    advanced_search, contact_thanks, contact, feeds, coverage_graph, faq, about, \
    browser_warning, serve_static_file, old_terms, latest_terms, contribute

mime_types = ('pdf', 'wpd', 'txt', 'doc', 'html', 'mp3')


urlpatterns = patterns('',
    # Footer stuff
    (r'^about/$', about),
    (r'^faq/$', faq),
    (r'^coverage/$', coverage_graph),
    (r'^feeds/$', feeds),
    (r'^contribute/$', contribute),
    (r'^contact/$', contact),
    (r'^contact/thanks/$', contact_thanks),

    # Serve a static file
    (r'^(?P<file_path>(?:' + "|".join(mime_types) + ')/.*)$',
     serve_static_file),

    # Advanced search page
    (r'^search/advanced-techniques/$', advanced_search),

    (r'^terms/v/(\d{1,2})/$', old_terms),
    (r'^terms/$', latest_terms),

    # Randoms
    (r'^tools/$', tools_page),
    (r'^bad-browser/$', browser_warning),

    # Robots
    (r'^robots.txt$', robots),

    # SEO-related stuff
    (r'^BingSiteAuth.xml$', validate_for_bing),
    (r'^googleef3d845637ccb353.html$', validate_for_google),
    (r'^google646349975c2495b6.html$', validate_for_google2),
    (r'^mywot8f5568174e171ff0acff.html$', validate_for_wot),

    # Favicon, touch icons, etc.
    (r'^favicon\.ico$',
     RedirectView.as_view(
         url='/static/ico/favicon.ico',
         permanent=True)),
    (r'^apple-touch-icon\.png$',
     RedirectView.as_view(
         url='/static/png/apple-touch-icon.png',
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
     RedirectView.as_view(
         url='/static/png/apple-touch-icon-precomposed.png',
         permanent=True)),
    # hopscotch http://127.0.0.1:8000/static/img/sprite-green.png
    (r'^static/img/sprite-green\.png$',
     RedirectView.as_view(
         url='/static/png/sprite-green.png',
         permanent=True)),
    (r'^static/img/sprite-orange\.png$',
     RedirectView.as_view(
         url='/static/png/sprite-orange.png',
         permanent=True)),
)


