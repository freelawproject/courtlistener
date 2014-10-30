from alert.opinion_page.views import redirect_opinion_pages, \
    redirect_cited_by_feeds
from alert.search.models import Court
from alert.simple_pages.views import show_maintenance_warning
from alert.sitemap import index_sitemap_maker
from django.conf.urls import include, patterns, url
from django.contrib import admin
from django.views.generic import RedirectView


pacer_codes = Court.objects.filter(in_use=True).values_list('pk', flat=True)

admin.autodiscover()

urlpatterns = patterns('',
    # Admin docs and site
    (r'^admin/doc/', include('django.contrib.admindocs.urls')),
    (r'^admin/', include(admin.site.urls)),

    # Maintenance and SOPA/PIPA mode! Must be here so it intercepts any other
    # urls.
    #(r'/*', show_maintenance_warning),

    url('', include('alert.audio.urls')),
    url('', include('alert.opinion_page.urls')),
    url('', include('alert.simple_pages.urls')),
    url('', include('alert.userHandling.urls')),
    url('', include('alert.favorites.urls')),
    url('', include('alert.search.urls')),
    url('', include('alert.alerts.urls')),
    url('', include('alert.api.urls')),
    url('', include('alert.donate.urls')),

    # Sitemaps
    (r'^sitemap\.xml$', index_sitemap_maker),
)

urlpatterns += patterns(
    (r'^privacy/$', RedirectView.as_view(url='/terms/#privacy')),
    (r'^removal/$', RedirectView.as_view(url='/terms/#removal')),
    (r'^report/2010/$', RedirectView.as_view(
        url='https://www.ischool.berkeley.edu/files/student_projects/Final_Report_Michael_Lissner_2010-05-07_2.pdf')),
    (r'^report/2012/$', RedirectView.as_view(
        url='https://www.ischool.berkeley.edu/files/student_projects/mcdonald_rustad_report.pdf')),

    # Dump URLs changed 2013-11-07 and updated 2014-10-02
    (r'^dump-info/$', RedirectView.as_view(url='/api/bulk-info/')),
    (r'^dump-api/.*/(?P<court>all|%s)\.xml.gz$' % "|".join(pacer_codes),
     RedirectView.as_view(url='/api/bulk-data/%(court)s.tar.gz')),

    # Bulk data URLs updated 2014-10-02
    (r'^api/bulk/.*/(?P<court>all|%s)\.xml.gz$' % "|".join(pacer_codes),
     RedirectView.as_view(url='/api/bulk-data/%(court)s.tar.gz')),

    # Court stripped from the URL on 2014-09-30
    (r'^(?:%s)/(.*)/(.*)/authorities/$' % "|".join(pacer_codes), redirect_opinion_pages),
    (r'^(?:%s)/(.*)/(.*)/cited-by/$' % "|".join(pacer_codes), redirect_opinion_pages),
    (r'^(?:%s)/(.*)/(.*)/$' % "|".join(pacer_codes), redirect_opinion_pages),
    (r'^feed/(.*)/cited-by/$', redirect_cited_by_feeds),
)
