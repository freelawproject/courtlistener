import operator
from functools import reduce

from asgiref.sync import sync_to_async
from django.db.models import (
    Case,
    Exists,
    IntegerField,
    OuterRef,
    Prefetch,
    Q,
    Value,
    When,
)
from django.http import HttpRequest, HttpResponse
from django.shortcuts import aget_object_or_404
from django.template.response import TemplateResponse
from django.urls import reverse
from judge_pics.search import ImageSizes, portrait

from cl.disclosures.models import FinancialDisclosure
from cl.people_db.models import Person, Position


def build_hit_count_annotation(search_terms: list[str]) -> Case:
    """Build a SQL annotation that counts how many name fields match search
    terms.

    For each name field (first, middle, last, suffix), adds 1 to hit_count if
    the lowercased field value exactly matches any search term. This scoring is
    done entirely in SQL for efficiency.

    :param search_terms: List of lowercase search terms
    :return: Sum of Case expressions that can be used as an annotation
    """
    hit_cases = []
    for field in ["name_first", "name_last", "name_middle", "name_suffix"]:
        # Build OR condition: field matches any search term (case-insensitive exact)
        conditions = [Q(**{f"{field}__iexact": term}) for term in search_terms]
        combined = reduce(operator.or_, conditions)
        hit_cases.append(
            Case(
                When(combined, then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            )
        )
    # Sum all cases
    return sum(hit_cases[1:], hit_cases[0])


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

    Search terms are split by spaces and matched against first, middle, last
    name and suffix. Results are sorted by the number of name components that
    exactly match search terms (scored in SQL for efficiency).
    """
    query = request.GET.get("q", "").strip()

    # Require at least 2 characters
    if len(query) < 2:
        return HttpResponse("")

    # Split query into terms (limit to 7 to prevent DOS)
    search_terms = [term.lower() for term in query.split()][:7]

    # Build search args - each term is matched against all four name fields
    # using istartswith for the initial filter
    search_args = []
    for term in search_terms:
        for field in (
            "name_first__istartswith",
            "name_last__istartswith",
            "name_middle__istartswith",
            "name_suffix__istartswith",
        ):
            search_args.append(Q(**{field: term}))

    # Build hit count annotation for sorting (counts exact matches in SQL)
    hit_count_annotation = build_hit_count_annotation(search_terms)

    # Query for people with disclosures matching the search
    # Annotate with hit_count and order by it (descending) to get best matches first
    name_query = reduce(operator.or_, search_args)
    people = await sync_to_async(list)(
        Person.objects.filter(
            # Only return people that have disclosure sub-objects
            Exists(
                FinancialDisclosure.objects.filter(
                    person=OuterRef("pk"),
                ).only("pk")
            ),
            # Don't include aliases
            is_alias_of=None,
        )
        .filter(name_query)
        .annotate(hit_count=hit_count_annotation)
        .order_by("-hit_count", "name_last", "name_first")
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
                .only("pk", "court_id", "person_id", "court__short_name")
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

        # Get URL to newest disclosure (build URL directly to avoid N+1 query
        # from get_absolute_url() accessing person.pk and person.slug)
        url = ""
        if hasattr(person, "disclosures") and person.disclosures:
            url = reverse(
                "financial_disclosures_viewer",
                args=(person.pk, person.disclosures[0].pk, person.slug),
            )

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
