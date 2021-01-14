from django.conf.urls import url

from cl.disclosures.views import (
    financial_disclosures_for_somebody,
    financial_disclosures_home,
)

urlpatterns = [
    url(
        r"^person/(?P<pk>\d+)/(?P<slug>[^/]*)/financial-disclosures/$",
        financial_disclosures_for_somebody,
        name="financial_disclosures_for_somebody",
    ),
    url(
        r"^financial-disclosures/$",
        financial_disclosures_home,
        name="financial_disclosures_home",
    ),
]
