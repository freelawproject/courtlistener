from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.utils.timezone import now

from cl.corpus_importer.forms import (
    EducationFormSet,
    PersonFilterForm,
    PersonForm,
    PoliticalAffiliationFormSet,
    PositionsFormSet,
    SourcesFormSet,
)
from cl.lib.search_utils import make_get_string
from cl.lib.types import AuthenticatedHttpRequest
from cl.people_db.models import Person, Source
from cl.people_db.utils import make_title_str
from cl.search.models import Court


@staff_member_required
def ca_judges(request: AuthenticatedHttpRequest) -> HttpResponse:
    """Show paginated judges from CA that can be updated by a researcher"""

    get_string = make_get_string(request)

    # Gather the judges and load the page
    cts = Court.objects.filter(
        Q(short_name__icontains="california")
        | Q(full_name__icontains="california"),
        jurisdiction__in=Court.STATE_JURISDICTIONS,
    )

    judge_list = (
        Person.objects.filter(
            is_alias_of__isnull=True,
            positions__court__in=cts,
            positions__date_termination=None,
        )
        .order_by("name_last", "name_first")
        .distinct()
    )

    # Filter to any names, jurisdictions, etc.
    form = PersonFilterForm(request.GET)
    if form.is_valid():
        cd = form.cleaned_data
        if cd.get("name"):
            name = cd["name"]
            judge_list = judge_list.filter(
                Q(name_last__iexact=name) | Q(name_first__iexact=name)
            )
        if cd.get("court_type"):
            judge_list = judge_list.filter(
                positions__court__jurisdiction=cd["court_type"]
            )
        if cd.get("court"):
            judge_list = judge_list.filter(positions__court=cd["court"])

    # Paginate to a single judge at a time
    paginator = Paginator(judge_list, 1)
    page = request.GET.get("page", 1)
    try:
        judge_page = paginator.page(page)
    except PageNotAnInteger:
        judge_page = paginator.page(1)
    except EmptyPage:
        judge_page = paginator.page(paginator.num_pages)

    # Abort if we don't have judges after filtering or whatever.
    if len(judge_page) == 0:
        raise Http404("No judge found. :(")

    judge = judge_page[0]
    qs_education = judge.educations.all()
    qs_politics = judge.political_affiliations.all()
    qs_positions = judge.positions.all()
    qs_sources = judge.sources.all()
    if request.method == "POST":
        # Update the record and redirect to the next one
        person_form = PersonForm(request.POST, instance=judge)
        education_formset = EducationFormSet(
            request.POST,
            queryset=qs_education,
            instance=judge,
        )
        politics_formset = PoliticalAffiliationFormSet(
            request.POST,
            queryset=qs_politics,
            instance=judge,
        )
        positions_formset = PositionsFormSet(
            request.POST,
            queryset=qs_positions,
            instance=judge,
        )
        sources_formset = SourcesFormSet(
            request.POST,
            queryset=qs_sources,
            instance=judge,
        )
        if all(
            [
                person_form.is_valid(),
                education_formset.is_valid(),
                politics_formset.is_valid(),
                positions_formset.is_valid(),
                sources_formset.is_valid(),
            ]
        ):
            person_form.save()
            education_formset.save()
            politics_formset.save()
            positions_formset.save()
            sources_formset.save()
            manual_source, created = Source.objects.get_or_create(
                person=judge,
                url="https://www.courtlistener.com",
                notes=f"Data updated by: {request.user.username}",
                defaults={"date_accessed": now().today()},
            )
            if created:
                judge.sources.add(manual_source)
            return HttpResponseRedirect(
                f"{request.path}?{get_string}&page={judge_page.next_page_number()}"
            )
    else:
        # Just a regular GET. Load the forms with the current data
        person_form = PersonForm(instance=judge)
        education_formset = EducationFormSet(
            queryset=qs_education,
            instance=judge,
        )
        politics_formset = PoliticalAffiliationFormSet(
            queryset=qs_politics,
            instance=judge,
        )
        positions_formset = PositionsFormSet(
            queryset=qs_positions,
            instance=judge,
        )
        sources_formset = SourcesFormSet(
            queryset=qs_sources,
            instance=judge,
        )

    return render(
        request,
        "ca_judges_input.html",
        {
            # The judge
            "judge_page": judge_page,
            "judge": judge,
            "title": make_title_str(judge),
            # Forms
            "person_form": person_form,
            "education_formset": education_formset,
            "politics_formset": politics_formset,
            "positions_formset": positions_formset,
            "sources_formset": sources_formset,
            # Etc
            "get_string": get_string,
            "private": True,
        },
    )
