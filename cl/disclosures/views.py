from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render

from cl.disclosures.models import FinancialDisclosure
from cl.disclosures.utils import make_disclosure_data
from cl.people_db.models import Person
from cl.people_db.utils import make_title_str


def financial_disclosures_home(request: HttpRequest) -> HttpResponse:
    """The home page for financial disclosures

    This page shows:
     - A brief introduction to financial disclosure reports
     - A list of all the people we have reports for
     - A simple JS filter to find specific judges
    """
    people_with_disclosures = Person.objects.filter(
        financial_disclosures__isnull=False,
    ).distinct()
    disclosure_count = FinancialDisclosure.objects.all().count()
    people_count = people_with_disclosures.count()
    return render(
        request,
        "financial_disclosures_home.html",
        {
            "people": people_with_disclosures,
            "disclosure_count": disclosure_count,
            "people_count": people_count,
            "private": False,
        },
    )


def financial_disclosures_viewer(
    request: HttpRequest,
    person_pk: int,
    pk: int,
    slug: str,
) -> HttpResponse:
    """Show the financial disclosures for a particular person"""
    person = get_object_or_404(Person, pk=person_pk)
    title = make_title_str(person)
    years, ids = make_disclosure_data(person)

    return render(
        request,
        "financial_disclosures_viewer.html",
        {
            "person": person,
            "title": title,
            "disclosure_years": years,
            "disclosure_ids": ids,
            "private": False,
        },
    )
