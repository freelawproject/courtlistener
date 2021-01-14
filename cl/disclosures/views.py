from django.http import HttpResponse, HttpRequest
from django.shortcuts import render, get_object_or_404

from cl.disclosures.models import FinancialDisclosure
from cl.people_db.models import Person
from cl.people_db.views import make_title_str


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


def financial_disclosures_for_somebody(
    request: HttpRequest,
    pk: int,
    slug: str,
) -> HttpResponse:
    """Show the financial disclosures for a particular person"""
    person = get_object_or_404(Person, pk=pk)
    title = make_title_str(person)
    return render(
        request,
        "financial_disclosures_for_somebody.html",
        {"person": person, "title": title, "private": False},
    )
