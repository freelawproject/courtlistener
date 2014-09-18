from django.conf.urls import patterns

urlpatterns = patterns('simple_pages.views',
    # Footer stuff
    (r'^about/$', 'about'),
    (r'^faq/$', 'faq'),
    (r'^coverage/$', 'coverage_graph'),
    (r'^feeds/$', 'feeds'),
    (r'^contact/$', 'contact'),
    (r'^contact/thanks/$', 'contact_thanks'),

    # Advanced search page
    (r'^search/advanced-techniques/$', 'advanced_search'),

    # Robots
    (r'^robots.txt$', 'robots'),

    # SEO-related stuff
    (r'^BingSiteAuth.xml$', 'validate_for_bing'),
    (r'^googleef3d845637ccb353.html$', 'validate_for_google'),
    (r'^google646349975c2495b6.html$', 'validate_for_google2'),
    (r'^mywot8f5568174e171ff0acff.html$', 'validate_for_wot'),
)


