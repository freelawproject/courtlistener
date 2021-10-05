from django.urls import path

from cl.disclosures.views import (
    financial_disclosures_home,
    financial_disclosures_viewer,
)

urlpatterns = [
    path(
        "person/<int:person_pk>/disclosure/<int:pk>/<blank-slug:slug>/",
        financial_disclosures_viewer,
        name="financial_disclosures_viewer",
    ),
    path(
        "financial-disclosures/",
        financial_disclosures_home,
        name="financial_disclosures_home",
    ),
]
