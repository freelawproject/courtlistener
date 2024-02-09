from django.http import HttpRequest, HttpResponse
from django.shortcuts import aget_object_or_404
from django.template.response import TemplateResponse

from cl.disclosures.models import FinancialDisclosure
from cl.disclosures.utils import make_disclosure_data
from cl.people_db.models import Person
from cl.people_db.utils import make_title_str


async def financial_disclosures_home(request: HttpRequest) -> HttpResponse:
    """The home page for financial disclosures

    This page shows:
     - A brief introduction to financial disclosure reports
     - A list of all the people we have reports for
     - A simple JS filter to find specific judges
    """
    people_with_disclosures = Person.objects.filter(
        financial_disclosures__isnull=False,
    ).distinct()
    disclosure_count = await FinancialDisclosure.objects.all().acount()
    people_count = await people_with_disclosures.acount()
    return TemplateResponse(
        request,
        "financial_disclosures_home.html",
        {
            "people": people_with_disclosures,
            "disclosure_count": disclosure_count,
            "people_count": people_count,
            "private": False,
        },
    )


async def financial_disclosures_viewer(
    request: HttpRequest,
    person_pk: int,
    pk: int,
    slug: str,
) -> HttpResponse:
    """Show the financial disclosures for a particular person"""
    queryset = Person.objects.prefetch_related("positions__court")
    person = await aget_object_or_404(queryset, pk=person_pk)
    title = await make_title_str(person)
    years, ids = await make_disclosure_data(person)

    return TemplateResponse(
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
