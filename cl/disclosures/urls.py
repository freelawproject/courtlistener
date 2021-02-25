from django.urls import path

from cl.disclosures.views import (
    financial_disclosures_for_somebody,
    financial_disclosures_home,
)

urlpatterns = [
    path(
        "person/<int:pk>/<slug:slug>/financial-disclosures/",
        financial_disclosures_for_somebody,
        name="financial_disclosures_for_somebody",
    ),
    path(
        "financial-disclosures/",
        financial_disclosures_home,
        name="financial_disclosures_home",
    ),
]
