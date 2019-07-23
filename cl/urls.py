from django.conf.urls import include, url
from django.contrib import admin
from django.views.generic import RedirectView
from cl.sitemap import index_sitemap_maker
from cl.simple_pages.views import serve_static_file

urlpatterns = [
    # Admin docs and site
    url(r'^admin/', admin.site.urls),

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
    url('', include('cl.stats.urls')),

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
        url='https://www.ischool.berkeley.edu/files/student_projects/Final_Report_Michael_Lissner_2010-05-07_2.pdf',  # noqa: E501
        permanent=True,
    )),
    url(r'^report/2012/$', RedirectView.as_view(
        url='https://www.ischool.berkeley.edu/files/student_projects/mcdonald_rustad_report.pdf',  # noqa: E501
        permanent=True,
    )),
    url(r'report/2013/$', RedirectView.as_view(
        url='https://github.com/freelawproject/related-literature/raw/master/CourtListener%20Studies/Sarah%20Tyler/sarah_tyler_dissertation.pdf',  # noqa: E501
        permanent=True,
    )),

    # Catch-alls that could conflict with other regexps -- place them last
    #   Serve a static file
    url(r'^(?P<file_path>(?:pdf|wpd|txt|doc|docx|html|mp3|recap)/.+)$',
        serve_static_file),
]
