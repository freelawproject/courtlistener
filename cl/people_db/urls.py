from cl.people_db.sitemap import people_sitemap_maker
from cl.people_db.views import view_person, financial_disclosures_home
from django.conf.urls import url


urlpatterns = [
    url(
        r'^person/(?P<pk>\d*)/(?P<slug>[^/]*)/$',
        view_person,
        name='view_person'
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
