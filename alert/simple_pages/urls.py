from django.conf.urls import patterns

urlpatterns = patterns('simple_pages.views',
    # Footer stuff
    (r'^about/$', 'about'),
    (r'^faq/$', 'faq'),
    (r'^coverage/$', 'coverage_graph'),
    (r'^contact/$', 'contact'),
    (r'^contact/thanks/$', 'contact_thanks'),

    # Advanced search page
    (r'^search/advanced-techniques/$', 'advanced_search'),

    # Robots
    (r'^robots.txt$', 'robots'),
)


