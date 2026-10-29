from django.conf import settings
from django.http import HttpResponseRedirect
from django.shortcuts import aget_object_or_404
from django.template.response import TemplateResponse
from django.urls import reverse
from judge_pics.search import ImageSizes, portrait

from cl.favorites.decorators import track_view_counter
from cl.people_db.models import Person
from cl.people_db.utils import make_title_str


@track_view_counter(tracks="person", label_format="p.%s:view")
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
            "ftm_last_updated": settings.FTM_LAST_UPDATED,
            "private": False,
        },
    )
