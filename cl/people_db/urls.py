from cl.people_db.views import view_person
from django.conf.urls import url


urlpatterns = [
    url(
        r'^person/(?P<pk>\d*)/(?P<slug>[^/]*)/$',
        view_person,
        name='view_person'
    ),
]
