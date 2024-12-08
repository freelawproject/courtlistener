from asgiref.sync import sync_to_async
from django.conf import settings
from django.http import HttpResponseRedirect
from django.shortcuts import aget_object_or_404
from django.template.response import TemplateResponse
from django.urls import reverse
from elasticsearch.exceptions import RequestError, TransportError
from elasticsearch_dsl import MultiSearch
from elasticsearch_dsl.response import Response
from judge_pics.search import ImageSizes, portrait

from cl.people_db.models import Person
from cl.people_db.utils import (
    build_authored_opinions_query,
    build_oral_arguments_heard,
    build_recap_cases_assigned_query,
    make_title_str,
)
from cl.search.documents import (
    AudioDocument,
    DocketDocument,
    OpinionClusterDocument,
)


async def view_person(request, pk, slug):
    queryset = Person.objects.select_related("is_alias_of").prefetch_related(
        "positions__court"
    )
    person = await aget_object_or_404(queryset, pk=pk)
    # Redirect the user if they're trying to check out an alias.
    if person.is_alias:
        return HttpResponseRedirect(
            reverse(
                "view_person",
                args=[person.is_alias_of.pk, person.is_alias_of.slug],
            )
        )

    title = await make_title_str(person)

    img_path = portrait(person.id, ImageSizes.LARGE)

    # Regroup the positions by whether they're judgeships or other. This allows
    # us to use the {% ifchanged %} template tags to have two groups in the
    # template.
    judicial_positions = []
    other_positions = []
    async for p in person.positions.all().order_by("-date_start"):
        if p.is_judicial_position:
            judicial_positions.append(p)
        else:
            other_positions.append(p)
    positions = judicial_positions + other_positions

    # Use Elasticsearch to get relevant opinions that the person wrote, related
    # RECAP cases or related Oral arguments.
    @sync_to_async
    def get_related_content_from_es(person_id: int) -> Response | None:
        """Use a single ES request to retrieve content related to a person."""
        authored_opinions_query = build_authored_opinions_query(
            OpinionClusterDocument.search(), person_id
        )
        oral_arguments_heard_query = build_oral_arguments_heard(
            AudioDocument.search(), person_id
        )
        recap_cases_assigned_query = build_recap_cases_assigned_query(
            DocketDocument.search(), person_id
        )
        multi_search = MultiSearch()
        multi_search = (
            multi_search.add(authored_opinions_query)
            .add(oral_arguments_heard_query)
            .add(recap_cases_assigned_query)
        )

        try:
            return multi_search.execute()
        except (TransportError, ConnectionError, RequestError):
            return None

    people_content_response = await get_related_content_from_es(person.id)
    authored_opinions = (
        people_content_response[0] if people_content_response else []
    )
    oral_arguments_heard = (
        people_content_response[1] if people_content_response else []
    )
    recap_cases_assigned = (
        people_content_response[2] if people_content_response else []
    )

    return TemplateResponse(
        request,
        "view_person.html",
        {
            "person": person,
            "title": title,
            "img_path": img_path,
            "aba_ratings": person.aba_ratings.all().order_by("-year_rated"),
            "political_affiliations": (
                person.political_affiliations.all().order_by("-date_start")
            ),
            "disclosures": person.financial_disclosures.all().order_by("year"),
            "positions": positions,
            "educations": person.educations.all().order_by("-degree_year"),
            "authored_opinions": authored_opinions,
            "oral_arguments_heard": oral_arguments_heard,
            "recap_cases_assigned": recap_cases_assigned,
            "ftm_last_updated": settings.FTM_LAST_UPDATED,
            "private": False,
        },
    )
