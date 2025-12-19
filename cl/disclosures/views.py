from asgiref.sync import sync_to_async
from django.db.models import Exists, OuterRef, Prefetch, Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import aget_object_or_404
from django.template.response import TemplateResponse
from judge_pics.search import ImageSizes, portrait

from cl.disclosures.models import FinancialDisclosure
from cl.people_db.models import Person, Position


async def financial_disclosures_home(request: HttpRequest) -> HttpResponse:
    """The home page for financial disclosures

    This page shows:
     - A brief introduction to financial disclosure reports
     - A search box to find judges by name
     - Information about the database and coverage
    """
    disclosure_count = await FinancialDisclosure.objects.all().acount()
    people_count = (
        await Person.objects.filter(
            financial_disclosures__isnull=False,
        )
        .distinct()
        .acount()
    )
    return TemplateResponse(
        request,
        "financial_disclosures_home.html",
        {
            "disclosure_count": disclosure_count,
            "people_count": people_count,
            "private": False,
        },
    )


async def disclosure_typeahead(request: HttpRequest) -> HttpResponse:
    """Return HTML partial with typeahead search results for judges.

    This endpoint supports HTMX-based typeahead search on the disclosures
    home page. Returns an HTML partial with matching judges.
    """
    query = request.GET.get("q", "").strip()

    # Require at least 2 characters
    if len(query) < 2:
        return HttpResponse("")

    # Query for people with disclosures matching the search
    # Search across name fields since name_full is a property, not a DB field
    name_query = (
        Q(name_first__icontains=query)
        | Q(name_middle__icontains=query)
        | Q(name_last__icontains=query)
    )
    people = await sync_to_async(list)(
        Person.objects.filter(
            Exists(
                FinancialDisclosure.objects.filter(
                    person=OuterRef("pk"),
                ).only("pk")
            ),
            is_alias_of=None,
        )
        .filter(name_query)
        .prefetch_related(
            Prefetch(
                "financial_disclosures",
                queryset=FinancialDisclosure.objects.all()
                .only("year", "id", "person_id")
                .order_by("-year"),
                to_attr="disclosures",
            ),
            Prefetch(
                "positions",
                queryset=Position.objects.filter(court__isnull=False)
                .select_related("court")
                .only("pk", "court_id", "person_id")
                .order_by("-date_start"),
                to_attr="court_positions",
            ),
        )
        .only(
            "name_first",
            "name_middle",
            "name_last",
            "name_suffix",
            "has_photo",
            "slug",
        )[:5]
    )

    # Build results list with needed data
    results = []
    for person in people:
        position_str = ""
        if hasattr(person, "court_positions") and person.court_positions:
            position_str = person.court_positions[0].court.short_name

        thumbnail_path = portrait(person.id, ImageSizes.SMALL)

        # Get URL to newest disclosure
        url = ""
        if hasattr(person, "disclosures") and person.disclosures:
            url = person.disclosures[0].get_absolute_url()

        results.append(
            {
                "name_full": person.name_full,
                "position_str": position_str,
                "thumbnail_path": thumbnail_path,
                "url": url,
            }
        )

    return TemplateResponse(
        request,
        "includes/disclosure_typeahead_results.html",
        {"results": results},
    )


async def financial_disclosures_viewer(
    request: HttpRequest,
    person_pk: int,
    pk: int,
    slug: str,
) -> HttpResponse:
    """Show the financial disclosures for a particular person.

    Fetches the specific disclosure with all related data (investments, gifts,
    debts, etc.) and renders it as a static page with tables.
    """
    # Get the disclosure with all related data prefetched
    disclosure = await aget_object_or_404(
        FinancialDisclosure.objects.select_related("person").prefetch_related(
            "investments",
            "gifts",
            "debts",
            "positions",
            "spouse_incomes",
            "agreements",
            "non_investment_incomes",
            "reimbursements",
        ),
        pk=pk,
        person_id=person_pk,
    )

    person = disclosure.person

    # Get all disclosures for this person (for year tabs)
    all_disclosures = await sync_to_async(list)(
        FinancialDisclosure.objects.filter(person_id=person_pk)
        .order_by("year")
        .values("id", "year")
    )

    return TemplateResponse(
        request,
        "financial_disclosures_viewer.html",
        {
            "disclosure": disclosure,
            "person": person,
            "all_disclosures": all_disclosures,
            "private": False,
        },
    )
