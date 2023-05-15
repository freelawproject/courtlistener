from django.conf import settings
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import reverse
from judge_pics.search import ImageSizes, portrait
from requests import Session

from cl.lib.scorched_utils import ExtraSolrInterface
from cl.people_db.models import Person
from cl.people_db.utils import make_title_str


def view_person(request, pk, slug):
    person = get_object_or_404(Person, pk=pk)
    # Redirect the user if they're trying to check out an alias.
    if person.is_alias:
        return HttpResponseRedirect(
            reverse(
                "view_person",
                args=[person.is_alias_of.pk, person.is_alias_of.slug],
            )
        )

    title = make_title_str(person)

    img_path = portrait(person.id, ImageSizes.LARGE)

    # Regroup the positions by whether they're judgeships or other. This allows
    # us to use the {% ifchanged %} template tags to have two groups in the
    # template.
    judicial_positions = []
    other_positions = []
    for p in person.positions.all().order_by("-date_start"):
        if p.is_judicial_position:
            judicial_positions.append(p)
        else:
            other_positions.append(p)
    positions = judicial_positions + other_positions

    # Use Solr to get relevant opinions that the person wrote
    with Session() as session:
        conn = ExtraSolrInterface(
            settings.SOLR_OPINION_URL, http_connection=session, mode="r"
        )
        q = {
            "q": f"author_id:{person.pk} OR panel_ids:{person.pk}",
            "fl": [
                "id",
                "court_id",
                "caseName",
                "absolute_url",
                "court",
                "court_citation_string",
                "dateFiled",
                "docketNumber",
                "citeCount",
                "status",
                "citation",
            ],
            "rows": 5,
            "start": 0,
            "sort": "dateFiled desc",
            "caller": "view_person",
        }
        authored_opinions = conn.query().add_extra(**q).execute()
    # Use Solr to get the oral arguments for the judge
    with Session() as session:
        conn = ExtraSolrInterface(
            settings.SOLR_AUDIO_URL, http_connection=session, mode="r"
        )
        q = {
            "q": f"panel_ids:{person.pk}",
            "fl": [
                "id",
                "absolute_url",
                "caseName",
                "court_id",
                "dateArgued",
                "docketNumber",
                "court_citation_string",
            ],
            "rows": 5,
            "start": 0,
            "sort": "dateArgued desc",
            "caller": "view_person",
        }
        oral_arguments_heard = conn.query().add_extra(**q).execute()
    with Session() as session:
        conn = ExtraSolrInterface(
            settings.SOLR_RECAP_URL, http_connection=session, mode="r"
        )
        q = {
            "q": f"assigned_to_id:{person.pk} OR referred_to_id:{person.pk}",
            "fl": [
                "id",
                "docket_absolute_url",
                "caseName",
                "court_citation_string",
                "dateFiled",
                "docketNumber",
            ],
            "group": "true",
            "group.ngroups": "true",
            "group.limit": 1,
            "group.field": "docket_id",
            "group.sort": "dateFiled desc",
            "rows": 5,
            "start": 0,
            "sort": "dateFiled desc",
            "caller": "view_person",
        }
        recap_cases_assigned = conn.query().add_extra(**q).execute()
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
