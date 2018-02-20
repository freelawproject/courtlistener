from cl.people_db.sitemap import people_sitemap_maker
from cl.people_db.views import financial_disclosures_for_somebody, \
    financial_disclosures_fileserver, view_person, financial_disclosures_home
from django.conf.urls import url


urlpatterns = [
    url(
        r'^person/(?P<pk>\d*)/(?P<slug>[^/]*)/$',
        view_person,
        name='view_person'
    ),
    url(
        r'^person/(?P<pk>\d*)/(?P<slug>[^/]*)/financial-disclosures/$',
        financial_disclosures_for_somebody,
        name='financial_disclosures_for_somebody',
    ),
    # Serve the PDFs, TIFFS, and thumbnails
    url(
        r'^person/'
        r'(?P<pk>\d*)/'
        r'(?P<slug>[^/]*)/'
        r'(?P<filepath>financial-disclosures/'
        r'(?:thumbnails/)?'
        r'.+\.(?:pdf|tiff|png))$',
        financial_disclosures_fileserver,
        name='financial_disclosures_fileserver',
    ),
    url(
        r'^financial-disclosures/$',
        financial_disclosures_home,
        name='financial_disclosures_home'
    ),

    # Sitemap
    url(
        r'^sitemap-people\.xml',
        people_sitemap_maker,
        name="people_sitemap",
    ),
]
