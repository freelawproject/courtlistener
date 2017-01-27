from django.conf.urls import include, url
from django.contrib import admin
from django.views.generic import RedirectView
from cl.opinion_page.views import redirect_cited_by_feeds, \
    redirect_cited_by_page
from cl.sitemap import index_sitemap_maker

urlpatterns = [
    # Admin docs and site
    url(r'^admin/doc/', include('django.contrib.admindocs.urls')),
    url(r'^admin/', include(admin.site.urls)),

    url('', include('cl.audio.urls')),
    url('', include('cl.opinion_page.urls')),
    url('', include('cl.simple_pages.urls')),
    url('', include('cl.users.urls')),
    url('', include('cl.favorites.urls')),
    url('', include('cl.people_db.urls')),
    url('', include('cl.search.urls')),
    url('', include('cl.alerts.urls')),
    url('', include('cl.api.urls')),
    url('', include('cl.donate.urls')),
    url('', include('cl.visualizations.urls')),

    # Sitemaps
    url(r'^sitemap\.xml$', index_sitemap_maker),

    # Redirects
    url(r'^privacy/$', RedirectView.as_view(
        url='/terms/#privacy',
        permanent=True,
    )),
    url(r'^removal/$', RedirectView.as_view(
        url='/terms/#removal',
        permanent=True,
    )),
    url(r'^report/2010/$', RedirectView.as_view(
        url='https://www.ischool.berkeley.edu/files/student_projects/Final_Report_Michael_Lissner_2010-05-07_2.pdf',
        permanent=True,
    )),
    url(r'^report/2012/$', RedirectView.as_view(
        url='https://www.ischool.berkeley.edu/files/student_projects/mcdonald_rustad_report.pdf',
        permanent=True,
    )),
    url(r'report/2013/$', RedirectView.as_view(
        url='https://github.com/freelawproject/related-literature/raw/master/CourtListener%20Studies/Sarah%20Tyler/sarah_tyler_dissertation.pdf',
        permanent=True,
    )),
]
