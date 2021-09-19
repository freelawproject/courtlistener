from collections import OrderedDict, defaultdict
from itertools import groupby
from typing import Dict, Optional, Tuple, Union
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.models import AnonymousUser, User
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import F, IntegerField, Prefetch
from django.db.models.functions import Cast
from django.http import HttpRequest, HttpResponseRedirect
from django.http.response import Http404, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, render
from django.template import loader
from django.template.defaultfilters import slugify
from django.urls import reverse
from django.utils.safestring import SafeText
from django.utils.timezone import now
from django.views.decorators.cache import cache_page, never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.vary import vary_on_cookie
from reporters_db import (
    EDITIONS,
    NAMES_TO_EDITIONS,
    REPORTERS,
    VARIATIONS_ONLY,
)
from rest_framework.status import HTTP_300_MULTIPLE_CHOICES, HTTP_404_NOT_FOUND

from cl.alerts.models import DocketAlert
from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.favorites.forms import FavoriteForm
from cl.favorites.models import Favorite
from cl.lib.auth import group_required
from cl.lib.bot_detector import is_og_bot
from cl.lib.http import is_ajax
from cl.lib.model_helpers import choices_to_csv
from cl.lib.models import THUMBNAIL_STATUSES
from cl.lib.ratelimiter import ratelimit_if_not_whitelisted
from cl.lib.search_utils import (
    get_citing_clusters_with_cache,
    get_related_clusters_with_cache,
    make_get_string,
)
from cl.lib.string_utils import trunc
from cl.lib.thumbnails import make_png_thumbnail_for_instance
from cl.lib.url_utils import get_redirect_or_404
from cl.lib.utils import alphanumeric_sort
from cl.lib.view_utils import increment_view_count
from cl.opinion_page.forms import (
    CitationRedirectorForm,
    DocketEntryFilterForm,
    TennWorkersForm,
)
from cl.people_db.models import AttorneyOrganization, CriminalCount, Role
from cl.recap.constants import COURT_TIMEZONES
from cl.search.models import (
    Citation,
    Court,
    Docket,
    OpinionCluster,
    RECAPDocument,
)
from cl.search.views import do_search


def court_homepage(request: HttpRequest, pk: str) -> HttpResponse:
    if pk not in ["tennworkcompcl", "tennworkcompapp"]:
        raise Http404("Court pages only implemented for Tennessee so far.")

    render_dict = {
        # Load the render_dict with good results that can be shown in the
        # "Latest Cases" sections
        "results_compcl": do_search(
            request.GET.copy(),
            rows=5,
            override_params={
                "order_by": "dateFiled desc",
                "court": "tennworkcompcl",
            },
            facet=False,
        )["results"],
        "results_compapp": do_search(
            request.GET.copy(),
            rows=5,
            override_params={
                "order_by": "dateFiled desc",
                "court": "tennworkcompapp",
            },
            facet=False,
        )["results"],
        "private": False,
    }
    return render(request, "court.html", render_dict)


@group_required("tenn_work_uploaders")
def court_publish_page(request: HttpRequest, pk: int) -> HttpResponse:
    """Display upload form and intake Opinions for Tenn. Workers Comp Cl/App

    :param request: A GET or POST request for the page
    :param pk: The CL Court ID for each court
    """

    if pk not in ["tennworkcompcl", "tennworkcompapp"]:
        raise Http404("Court pages only implemented for Tennessee so far.")
    form = TennWorkersForm(pk=pk)
    if request.method == "POST":
        form = TennWorkersForm(request.POST, request.FILES, pk=pk)
        if form.is_valid():
            cluster = form.save()
            goto = reverse("view_case", args=[cluster.pk, cluster.slug])
            messages.info(
                request, "Document uploaded successfully.", extra_tags=goto
            )
            return HttpResponseRedirect(
                reverse("court_publish_page", kwargs={"pk": pk})
            )
        else:
            messages.info(
                request, "Error submitting form, please review below."
            )
    return render(
        request, "publish.html", {"form": form, "private": True, "pk": pk}
    )


def redirect_og_lookup(request: HttpRequest) -> HttpResponse:
    """Redirect an open graph bot to the page for a RECAP document so that
    it can get good thumbnails and metadata even though it's a PDF.

    If it hits an error, send the bot back to AWS to get the PDF, but set
    "no-og" parameter to be sure the file gets served.
    """
    file_path = get_redirect_or_404(request, "file_path")

    try:
        rd = RECAPDocument.objects.get(filepath_local=file_path)
    except (
        RECAPDocument.DoesNotExist,
        RECAPDocument.MultipleObjectsReturned,
    ):
        # We couldn't find the URL. Redirect back to AWS, but be sure to serve
        # the file this time. Ideally this doesn't happen, but let's be ready
        # in case it does.
        return HttpResponseRedirect(
            f"https://storage.courtlistener.com/{file_path}?no-og=1"
        )
    else:
        return view_recap_document(
            request,
            docket_id=rd.docket_entry.docket_id,
            doc_num=rd.document_number,
            att_num=rd.attachment_number,
        )


def redirect_docket_recap(
    request: HttpRequest,
    court: Court,
    pacer_case_id: str,
) -> HttpResponseRedirect:
    docket = get_object_or_404(
        Docket, pacer_case_id=pacer_case_id, court=court
    )
    return HttpResponseRedirect(
        reverse("view_docket", args=[docket.pk, docket.slug])
    )


def make_docket_title(docket: Docket) -> str:
    title = ", ".join(
        [
            s
            for s in [
                trunc(best_case_name(docket), 100, ellipsis="..."),
                docket.docket_number,
            ]
            if s and s.strip()
        ]
    )
    return title


def user_has_alert(user: Union[AnonymousUser, User], docket: Docket) -> bool:
    has_alert = False
    if user.is_authenticated:
        has_alert = DocketAlert.objects.filter(
            docket=docket, user=user
        ).exists()
    return has_alert


def core_docket_data(
    request: HttpRequest,
    pk: int,
) -> Tuple[Docket, Dict[str, Union[bool, str, Docket, FavoriteForm]]]:
    """Gather the core data for a docket, party, or IDB page."""
    docket = get_object_or_404(Docket, pk=pk)
    title = make_docket_title(docket)

    try:
        fave = Favorite.objects.get(docket_id=docket.pk, user=request.user)
    except (ObjectDoesNotExist, TypeError):
        # Not favorited or anonymous user
        favorite_form = FavoriteForm(
            initial={
                "docket_id": docket.pk,
                "name": trunc(best_case_name(docket), 100, ellipsis="..."),
            }
        )
    else:
        favorite_form = FavoriteForm(instance=fave)

    has_alert = user_has_alert(request.user, docket)

    return (
        docket,
        {
            "docket": docket,
            "title": title,
            "favorite_form": favorite_form,
            "has_alert": has_alert,
            "timezone": COURT_TIMEZONES.get(docket.court_id, "US/Eastern"),
            "private": docket.blocked,
        },
    )


@cache_page(60)
@vary_on_cookie
@ratelimit_if_not_whitelisted
def view_docket(request: HttpRequest, pk: int, slug: str) -> HttpResponse:
    docket, context = core_docket_data(request, pk)
    increment_view_count(docket, request)

    de_list = docket.docket_entries.all().prefetch_related("recap_documents")
    form = DocketEntryFilterForm(request.GET)
    if form.is_valid():
        cd = form.cleaned_data
        if cd.get("entry_gte"):
            de_list = de_list.filter(entry_number__gte=cd["entry_gte"])
        if cd.get("entry_lte"):
            de_list = de_list.filter(entry_number__lte=cd["entry_lte"])
        if cd.get("filed_after"):
            de_list = de_list.filter(date_filed__gte=cd["filed_after"])
        if cd.get("filed_before"):
            de_list = de_list.filter(date_filed__lte=cd["filed_before"])
        if cd.get("order_by") == DocketEntryFilterForm.DESCENDING:
            de_list = de_list.order_by(
                "-recap_sequence_number", "-entry_number"
            )

    paginator = Paginator(de_list, 200, orphans=10)
    page = request.GET.get("page", 1)
    try:
        docket_entries = paginator.page(page)
    except PageNotAnInteger:
        docket_entries = paginator.page(1)
    except EmptyPage:
        docket_entries = paginator.page(paginator.num_pages)

    context.update(
        {
            "parties": docket.parties.exists(),  # Needed to show/hide parties tab.
            "docket_entries": docket_entries,
            "form": form,
            "get_string": make_get_string(request),
        }
    )
    return render(request, "view_docket.html", context)


@ratelimit_if_not_whitelisted
def view_parties(
    request: HttpRequest,
    docket_id: int,
    slug: str,
) -> HttpResponse:
    """Show the parties and attorneys tab on the docket."""
    docket, context = core_docket_data(request, docket_id)

    # We work with this data at the level of party_types so that we can group
    # the parties by this field. From there, we do a whole mess of prefetching,
    # which reduces the number of queries needed for this down to four instead
    # of potentially thousands (good times!)
    party_types = (
        docket.party_types.select_related("party")
        .prefetch_related(
            Prefetch(
                "party__roles",
                queryset=Role.objects.filter(docket=docket)
                .order_by("attorney_id", "role", "role_raw", "date_action")
                .select_related("attorney")
                .prefetch_related(
                    Prefetch(
                        "attorney__organizations",
                        queryset=AttorneyOrganization.objects.filter(
                            attorney_organization_associations__docket=docket
                        ).distinct(),
                        to_attr="firms_in_docket",
                    )
                ),
            ),
            Prefetch(
                "criminal_counts",
                queryset=CriminalCount.objects.all().order_by("status"),
            ),
            "criminal_complaints",
        )
        .order_by("name", "party__name")
    )

    parties = []
    for party_type_name, party_types in groupby(party_types, lambda x: x.name):
        party_types = list(party_types)
        parties.append(
            {
                "party_type_name": party_type_name,
                "party_type_objects": party_types,
            }
        )

    context.update(
        {"parties": parties, "docket_entries": docket.docket_entries.exists()}
    )
    return render(request, "docket_parties.html", context)


@ratelimit_if_not_whitelisted
def docket_idb_data(
    request: HttpRequest,
    docket_id: int,
    slug: str,
) -> HttpResponse:
    docket, context = core_docket_data(request, docket_id)
    if docket.idb_data is None:
        raise Http404("No IDB data for this docket at this time")
    context.update(
        {
            # Needed to show/hide parties tab.
            "parties": docket.parties.exists(),
            "docket_entries": docket.docket_entries.exists(),
            "origin_csv": choices_to_csv(docket.idb_data, "origin"),
            "jurisdiction_csv": choices_to_csv(
                docket.idb_data, "jurisdiction"
            ),
            "arbitration_csv": choices_to_csv(
                docket.idb_data, "arbitration_at_filing"
            ),
            "class_action_csv": choices_to_csv(
                docket.idb_data, "termination_class_action_status"
            ),
            "procedural_progress_csv": choices_to_csv(
                docket.idb_data, "procedural_progress"
            ),
            "disposition_csv": choices_to_csv(docket.idb_data, "disposition"),
            "nature_of_judgment_csv": choices_to_csv(
                docket.idb_data, "nature_of_judgement"
            ),
            "judgment_csv": choices_to_csv(docket.idb_data, "judgment"),
            "pro_se_csv": choices_to_csv(docket.idb_data, "pro_se"),
        }
    )
    return render(request, "docket_idb_data.html", context)


def make_rd_title(rd: RECAPDocument) -> str:
    de = rd.docket_entry
    d = de.docket
    return "{desc}#{doc_num}{att_num} in {case_name} ({court}{docket_number})".format(
        desc="%s &ndash; " % rd.description if rd.description else "",
        doc_num=rd.document_number,
        att_num=", Att. #%s" % rd.attachment_number
        if rd.document_type == RECAPDocument.ATTACHMENT
        else "",
        case_name=best_case_name(d),
        court=d.court.citation_string,
        docket_number=f", {d.docket_number}" if d.docket_number else "",
    )


def make_thumb_if_needed(
    request: HttpRequest,
    rd: RECAPDocument,
) -> RECAPDocument:
    """Make a thumbnail for a RECAP Document, if needed

    If a thumbnail is needed, can be made and should be made, make one.

    :param request: The request sent to the server
    :param rd: A RECAPDocument object
    """
    needs_thumb = rd.thumbnail_status != THUMBNAIL_STATUSES.COMPLETE
    if all([needs_thumb, rd.has_valid_pdf, is_og_bot(request)]):
        make_png_thumbnail_for_instance(
            pk=rd.pk,
            klass=RECAPDocument,
            file_attr="filepath_local",
            max_dimension=1068,
        )
        rd.refresh_from_db()
    return rd


@ratelimit_if_not_whitelisted
def view_recap_document(
    request: HttpRequest,
    docket_id: Optional[int] = None,
    doc_num: Optional[int] = None,
    att_num: Optional[int] = None,
    slug: str = "",
) -> HttpResponse:
    """This view can either load an attachment or a regular document,
    depending on the URL pattern that is matched.
    """
    try:
        rd = RECAPDocument.objects.filter(
            docket_entry__docket__id=docket_id,
            document_number=doc_num,
            attachment_number=att_num,
        ).order_by("pk")[0]
    except IndexError:
        raise Http404("No RECAPDocument matches the given query.")

    title = make_rd_title(rd)
    rd = make_thumb_if_needed(request, rd)
    try:
        fave = Favorite.objects.get(recap_doc_id=rd.pk, user=request.user)
    except (ObjectDoesNotExist, TypeError):
        # Not favorited or anonymous user
        favorite_form = FavoriteForm(
            initial={
                "recap_doc_id": rd.pk,
                "name": trunc(title, 100, ellipsis="..."),
            }
        )
    else:
        favorite_form = FavoriteForm(instance=fave)

    return render(
        request,
        "recap_document.html",
        {
            "rd": rd,
            "title": title,
            "favorite_form": favorite_form,
            "private": True,  # Always True for RECAP docs.
        },
    )


@never_cache
@ratelimit_if_not_whitelisted
def view_opinion(request: HttpRequest, pk: int, _: str) -> HttpResponse:
    """Using the cluster ID, return the cluster of opinions.

    We also test if the cluster ID is a favorite for the user, and send data
    if needed. If it's a favorite, we send the bound form for the favorite so
    it can populate the form on the page. If it is not a favorite, we send the
    unbound form.
    """
    # Look up the court, cluster, title and favorite information
    cluster = get_object_or_404(OpinionCluster, pk=pk)
    title = ", ".join(
        [
            s
            for s in [
                trunc(best_case_name(cluster), 100, ellipsis="..."),
                cluster.citation_string,
            ]
            if s.strip()
        ]
    )
    has_downloads = False
    for sub_opinion in cluster.sub_opinions.all():
        if sub_opinion.local_path or sub_opinion.download_url:
            has_downloads = True
            break
    get_string = make_get_string(request)

    try:
        fave = Favorite.objects.get(cluster_id=cluster.pk, user=request.user)
    except (ObjectDoesNotExist, TypeError):
        # Not favorited or anonymous user
        favorite_form = FavoriteForm(
            initial={
                "cluster_id": cluster.pk,
                "name": trunc(best_case_name(cluster), 100, ellipsis="..."),
            }
        )
    else:
        favorite_form = FavoriteForm(instance=fave)

    citing_clusters, citing_cluster_count = get_citing_clusters_with_cache(
        cluster
    )

    (
        related_clusters,
        sub_opinion_ids,
        related_search_params,
    ) = get_related_clusters_with_cache(cluster, request)

    return render(
        request,
        "view_opinion.html",
        {
            "title": title,
            "cluster": cluster,
            "has_downloads": has_downloads,
            "favorite_form": favorite_form,
            "get_string": get_string,
            "private": cluster.blocked,
            "citing_clusters": citing_clusters,
            "citing_cluster_count": citing_cluster_count,
            "top_authorities": cluster.authorities_with_data[:5],
            "authorities_count": len(cluster.authorities_with_data),
            "sub_opinion_ids": sub_opinion_ids,
            "related_algorithm": "mlt",
            "related_clusters": related_clusters,
            "related_cluster_ids": [item["id"] for item in related_clusters],
            "related_search_params": f"&{urlencode(related_search_params)}",
        },
    )


@ratelimit_if_not_whitelisted
def view_authorities(request: HttpRequest, pk: int, slug: str) -> HttpResponse:
    cluster = get_object_or_404(OpinionCluster, pk=pk)

    return render(
        request,
        "view_opinion_authorities.html",
        {
            "title": "%s, %s"
            % (trunc(best_case_name(cluster), 100), cluster.citation_string),
            "cluster": cluster,
            "private": cluster.blocked or cluster.has_private_authority,
            "authorities_with_data": cluster.authorities_with_data,
        },
    )


@ratelimit_if_not_whitelisted
def cluster_visualizations(
    request: HttpRequest, pk: int, slug: str
) -> HttpResponse:
    cluster = get_object_or_404(OpinionCluster, pk=pk)
    return render(
        request,
        "view_opinion_visualizations.html",
        {
            "title": "%s, %s"
            % (trunc(best_case_name(cluster), 100), cluster.citation_string),
            "cluster": cluster,
            "private": cluster.blocked or cluster.has_private_authority,
        },
    )


def throw_404(request: HttpRequest, context: Dict) -> HttpResponse:
    return render(
        request,
        "volumes_for_reporter.html",
        context,
        status=HTTP_404_NOT_FOUND,
    )


def reporter_or_volume_handler(
    request: HttpRequest, reporter: str, volume: Optional[str] = None
) -> HttpResponse:
    """Show all the volumes for a given reporter abbreviation or all the cases
    for a reporter-volume dyad.

    Two things going on here:
    1. We don't know which reporter the user actually wants when they provide
       an ambiguous abbreviation. Just show them all.
    2. We want to also show off that we know all these reporter abbreviations.
    """
    root_reporter = EDITIONS.get(reporter)

    if not root_reporter:
        return throw_404(
            request,
            {"no_reporters": True, "reporter": reporter, "private": False},
        )

    volume_names = [r["name"] for r in REPORTERS[root_reporter]]
    variation_names = {}
    variation_abbrevs = VARIATIONS_ONLY.get(reporter, [])
    for abbrev in variation_abbrevs:
        for r in REPORTERS[abbrev]:
            if r["name"] not in volume_names:
                variation_names[r["name"]] = abbrev

    if volume is None:
        # Show all the volumes for the case
        volumes_in_reporter = list(
            Citation.objects.filter(reporter=reporter)
            .order_by("reporter", "volume")
            .values_list("volume", flat=True)
            .distinct()
        )

        if not volumes_in_reporter:
            return throw_404(
                request,
                {
                    "no_volumes": True,
                    "reporter": reporter,
                    "volume_names": volume_names,
                    "private": False,
                },
            )

        return render(
            request,
            "volumes_for_reporter.html",
            {
                "reporter": reporter,
                "volume_names": volume_names,
                "volumes": volumes_in_reporter,
                "variation_names": variation_names,
                "private": False,
            },
        )

    # Show all the cases for a volume-reporter dyad
    cases_in_volume = (
        OpinionCluster.objects.filter(
            citations__reporter=reporter, citations__volume=volume
        )
        .annotate(cite_page=(F("citations__page")))
        .order_by("cite_page")
    )
    cases_in_volume = alphanumeric_sort(cases_in_volume, "cite_page")

    if not cases_in_volume:
        return throw_404(
            request,
            {
                "no_cases": True,
                "reporter": reporter,
                "volume_names": volume_names,
                "volume": volume,
                "private": False,
            },
        )

    volumes = list(
        (
            Citation.objects.filter(reporter=reporter)
            .annotate(as_integer=Cast("volume", IntegerField()))
            .values_list("as_integer", flat=True)
            .distinct()
            .order_by("as_integer")
        )
    )
    index = volumes.index(int(volume))
    volume_previous = volumes[index - 1] if index > 0 else None
    volume_next = volumes[index + 1] if index + 1 < len(volumes) else None

    paginator = Paginator(cases_in_volume, 100, orphans=5)
    page = request.GET.get("page", 1)
    try:
        cases = paginator.page(page)
    except PageNotAnInteger:
        cases = paginator.page(1)
    except EmptyPage:
        cases = paginator.page(paginator.num_pages)

    return render(
        request,
        "volumes_for_reporter.html",
        {
            "cases": cases,
            "reporter": reporter,
            "variation_names": variation_names,
            "volume": volume,
            "volume_names": volume_names,
            "volume_previous": volume_previous,
            "volume_next": volume_next,
            "private": any([case.blocked for case in cases_in_volume]),
        },
    )


def make_reporter_dict() -> Dict:
    """Make a dict of reporter names and abbreviations

    The format here is something like:

        {
            "Atlantic Reporter": ['A.', 'A.2d', 'A.3d'],
        }
    """
    reporters_in_db = list(
        Citation.objects.order_by("reporter")
        .values_list("reporter", flat=True)
        .distinct()
    )

    reporters: Union[defaultdict, OrderedDict] = defaultdict(list)
    for name, abbrev_list in NAMES_TO_EDITIONS.items():
        for abbrev in abbrev_list:
            if abbrev in reporters_in_db:
                reporters[name].append(abbrev)
    reporters = OrderedDict(sorted(reporters.items(), key=lambda t: t[0]))
    return reporters


def citation_handler(
    request: HttpRequest,
    reporter: str,
    volume: str,
    page: str,
) -> HttpResponse:
    """Load the page when somebody looks up a complete citation"""

    citation_str = " ".join([volume, reporter, page])
    try:
        clusters = OpinionCluster.objects.filter(citation=citation_str)
    except ValueError:
        # Unable to parse the citation.
        cluster_count = 0
    else:
        cluster_count = clusters.count()

    if cluster_count == 0:
        # Do a second pass for the closest opinion and check if we have
        # a page cite that matches -- if it does give the requested opinion
        possible_match = (
            OpinionCluster.objects.filter(
                citations__reporter=reporter,
                citations__volume=volume,
            )
            .annotate(as_integer=Cast("citations__page", IntegerField()))
            .exclude(as_integer__gte=page)
            .order_by("-as_integer")
            .first()
        )

        if possible_match:
            # There may be different page cite formats that aren't yet
            # accounted for by this code.
            clusters = OpinionCluster.objects.filter(
                id=possible_match.id,
                sub_opinions__html_with_citations__contains=f"*{page}",
            )
            cluster_count = 1 if clusters else 0

    # Show the correct page....
    if cluster_count == 0:
        # No results for an otherwise valid citation.
        return render(
            request,
            "citation_redirect_info_page.html",
            {
                "none_found": True,
                "citation_str": citation_str,
                "private": False,
            },
            status=HTTP_404_NOT_FOUND,
        )

    if cluster_count == 1:
        # Total success. Redirect to correct location.
        return HttpResponseRedirect(clusters[0].get_absolute_url())

    if cluster_count > 1:
        # Multiple results. Show them.
        return HttpResponse(
            content=loader.render_to_string(
                "citation_redirect_info_page.html",
                {
                    "too_many": True,
                    "citation_str": citation_str,
                    "clusters": clusters,
                    "private": any([cluster.blocked for cluster in clusters]),
                },
                request=request,
            ),
            status=HTTP_300_MULTIPLE_CHOICES,
        )
    return HttpResponse(status=500)


def citation_redirector(
    request: HttpRequest,
    reporter: Optional[str] = None,
    volume: Optional[str] = None,
    page: Optional[str] = None,
) -> HttpResponse:
    """Take a citation URL and use it to redirect the user to the canonical
    page for that citation.

    This uses the same infrastructure as the thing that identifies citations in
    the text of opinions.
    """

    if request.method == "POST":
        form = CitationRedirectorForm(request.POST)
        if form.is_valid():
            # Redirect to the page as a GET instead of a POST
            cd = form.cleaned_data
            return HttpResponseRedirect(
                reverse("citation_redirector", kwargs=cd)
            )
        else:
            # Error in form, somehow.
            return render(
                request,
                "citation_redirect_info_page.html",
                {"show_homepage": True, "form": form, "private": False},
            )

    if all(_ is None for _ in (reporter, volume, page)):
        # No parameters. Show the citation lookup homepage.
        form = CitationRedirectorForm()
        reporter_dict = make_reporter_dict()
        return render(
            request,
            "citation_redirect_info_page.html",
            {
                "show_homepage": True,
                "reporter_dict": reporter_dict,
                "form": form,
                "private": False,
            },
        )

    if reporter:
        reporter_slug = slugify(reporter)
        if reporter != reporter_slug:
            # Reporter provided in non-slugified form. Redirect to slugified
            # version.
            cd = {"reporter": reporter_slug}
            if volume:
                cd["volume"] = volume
            if page:
                cd["page"] = page
            return HttpResponseRedirect(
                reverse("citation_redirector", kwargs=cd)
            )

    # Look up the slugified reporter to get its proper version (so-2d -> So. 2d)
    slug_edition = {slugify(item): item for item in EDITIONS.keys()}
    proper_reporter = slug_edition.get(SafeText(reporter), None)
    if not proper_reporter:
        return HttpResponse(status=404)
    # We have a reporter (show volumes in it), a volume (show cases in
    # it), or a citation (show matching citation(s))
    if proper_reporter and volume and page:
        return citation_handler(request, proper_reporter, volume, page)
    elif proper_reporter and volume and page is None:
        return reporter_or_volume_handler(request, proper_reporter, volume)
    elif proper_reporter and volume is None and page is None:
        return reporter_or_volume_handler(request, proper_reporter)
    return HttpResponse(status=500)


@ensure_csrf_cookie
def block_item(request: HttpRequest) -> HttpResponse:
    """Block an item from search results using AJAX"""
    if is_ajax(request) and request.user.is_superuser:
        obj_type = request.POST["type"]
        pk = request.POST["id"]
        if obj_type == "docket":
            # Block the docket
            d = get_object_or_404(Docket, pk=pk)
            d.blocked = True
            d.date_blocked = now()
            d.save()
        elif obj_type == "cluster":
            # Block the cluster and the docket
            cluster = get_object_or_404(OpinionCluster, pk=pk)
            cluster.blocked = True
            cluster.date_blocked = now()
            cluster.save(index=False)
            cluster.docket.blocked = True
            cluster.docket.date_blocked = now()
            cluster.docket.save()
        return HttpResponse("It worked")
    else:
        return HttpResponseNotAllowed(
            permitted_methods=["POST"], content="Not an ajax request"
        )
