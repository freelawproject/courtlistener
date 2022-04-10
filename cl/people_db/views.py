from django.conf import settings
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from judge_pics.search import ImageSizes, portrait

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

    # img_path = make_person_picture_path(person)
    img_path = portrait(person.id, ImageSizes.large)

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
    conn = ExtraSolrInterface(settings.SOLR_OPINION_URL, mode="r")
    q = {
        "q": "author_id:{p} OR panel_ids:{p}".format(p=person.pk),
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
        "sort": "score desc",
        "caller": "view_person",
    }
    authored_opinions = conn.query().add_extra(**q).execute()
    conn.conn.http_connection.close()
    # Use Solr to get the oral arguments for the judge
    conn = ExtraSolrInterface(settings.SOLR_AUDIO_URL, mode="r")
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
    conn.conn.http_connection.close()
    return render(
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
            "ftm_last_updated": settings.FTM_LAST_UPDATED,
            "private": False,
        },
    )
