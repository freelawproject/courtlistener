from django.urls import path

from cl.people_db.views import view_person

urlpatterns = [
    path(
        "person/<int:pk>/<blank-slug:slug>/",
        view_person,
        name="view_person",
    ),
]
