from django.conf.urls import url

from cl.people_db.views import view_person

urlpatterns = [
    url(
        r"^person/(?P<pk>\d+)/(?P<slug>[^/]*)/$",
        view_person,
        name="view_person",
    ),
]
