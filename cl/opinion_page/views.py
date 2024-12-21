import datetime
from collections import OrderedDict, defaultdict
from datetime import timedelta
from http import HTTPStatus
from typing import Any, Dict, Union
from urllib.parse import urlencode

import eyecite
import waffle
from asgiref.sync import async_to_sync, sync_to_async
from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import IntegerField, Prefetch, QuerySet
from django.db.models.functions import Cast
from django.http import HttpRequest, HttpResponseRedirect
from django.http.response import (
    Http404,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseNotAllowed,
)
from django.shortcuts import aget_object_or_404  # type: ignore[attr-defined]
from django.template.defaultfilters import slugify
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.timezone import now
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from eyecite.tokenizers import HyperscanTokenizer
from reporters_db import (
    EDITIONS,
    NAMES_TO_EDITIONS,
    REPORTERS,
    VARIATIONS_ONLY,
)
from seal_rookery.search import ImageSizes, seal

from cl.citations.parenthetical_utils import get_or_create_parenthetical_groups
from cl.citations.utils import (
    SLUGIFIED_EDITIONS,
    filter_out_non_case_law_citations,
    get_canonicals_from_reporter,
)
from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.favorites.forms import NoteForm
from cl.favorites.models import Note
from cl.favorites.utils import (
    get_existing_prayers_in_bulk,
    get_prayer_counts_in_bulk,
    prayer_eligible,
)
from cl.lib.auth import group_required
from cl.lib.bot_detector import is_og_bot
from cl.lib.decorators import cache_page_ignore_params
from cl.lib.http import is_ajax
from cl.lib.model_helpers import choices_to_csv
from cl.lib.models import THUMBNAIL_STATUSES
from cl.lib.ratelimiter import ratelimiter_all_10_per_h
from cl.lib.search_utils import make_get_string
from cl.lib.string_utils import trunc
from cl.lib.thumbnails import make_png_thumbnail_for_instance
from cl.lib.url_utils import get_redirect_or_abort
from cl.lib.view_utils import increment_view_count
from cl.opinion_page.feeds import DocketFeed
from cl.opinion_page.forms import (
    CitationRedirectorForm,
    DocketEntryFilterForm,
    MeCourtUploadForm,
    MissCourtUploadForm,
    MoCourtUploadForm,
    TennWorkCompAppUploadForm,
    TennWorkCompClUploadForm,
)
from cl.opinion_page.types import AuthoritiesContext
from cl.opinion_page.utils import (
    core_docket_data,
    es_cited_case_count,
    es_get_cited_clusters_with_cache,
    es_get_citing_and_related_clusters_with_cache,
    es_get_related_clusters_with_cache,
    es_related_case_count,
    generate_docket_entries_csv_data,
    get_case_title,
)
from cl.people_db.models import AttorneyOrganization, CriminalCount, Role
from cl.recap.constants import COURT_TIMEZONES
from cl.recap.models import FjcIntegratedDatabase
from cl.search.models import (
    SEARCH_TYPES,
    Citation,
    Court,
    Docket,
    DocketEntry,
    Opinion,
    OpinionCluster,
    Parenthetical,
    RECAPDocument,
)
from cl.search.selectors import get_clusters_from_citation_str
from cl.search.views import do_es_search

HYPERSCAN_TOKENIZER = HyperscanTokenizer(cache_dir=".hyperscan")


async def court_homepage(request: HttpRequest, pk: str) -> HttpResponse:
    """Individual Court Home Pages"""

    available_courts = [
        "tennworkcompcl",
        "tennworkcompapp",
        "me",
        "mo",
        "moctapped",
        "moctappsd",
        "moctappwd",
        "miss",
        "missctapp",
    ]

    if pk not in available_courts:
        raise Http404("Court pages only implemented for select courts.")

    render_court = await Court.objects.aget(pk=pk)
    render_dict = {
        "private": False,
        "pk": pk,
        "court": render_court.full_name,
    }

    if pk == "tennworkcompapp" or pk == "tennworkcompcl":
        courts = ["tennworkcompcl", "tennworkcompapp"]
        template = "tn-court.html"
    else:
        courts = [pk]
        template = "court.html"

    court_seal = seal(pk, ImageSizes.SMALL)
    if "moctapp" in pk:
        # return mo seal
        court_seal = seal("mo", ImageSizes.SMALL)
    if "tennworkcomp" in pk:
        # return tenn seal
        court_seal = seal("tenn", ImageSizes.SMALL)

    render_dict["court_seal"] = court_seal

    for court in courts:
        if "tennwork" in court:
            results = f"results_{court}"
        else:
            results = "results"

        mutable_GET = request.GET.copy()
        # Do es search
        mutable_GET.update(
            {
                "order_by": "dateFiled desc",
                "type": SEARCH_TYPES.OPINION,
                "court": court,
                "filed_after": (
                    datetime.datetime.today() - datetime.timedelta(days=28)  # type: ignore
                ),
            }
        )
        response = await sync_to_async(do_es_search)(mutable_GET)

        render_dict[results] = response["results"]
    return TemplateResponse(request, template, render_dict)


@group_required(
    "tenn_work_uploaders",
    "uploaders_tennworkcompcl",
    "uploaders_tennworkcompapp",
    "uploaders_me",
    "uploaders_mo",
    "uploaders_moctapped",
    "uploaders_moctappsd",
    "uploaders_moctappwd",
    "uploaders_miss",
    "uploaders_missctapp",
)
async def court_publish_page(request: HttpRequest, pk: str) -> HttpResponse:
    """Display upload form and intake Opinions for partner courts

    :param request: A GET or POST request for the page
    :param pk: The CL Court ID for each court
    """

    available_courts = [
        "tennworkcompcl",
        "tennworkcompapp",
        "me",
        "mo",
        "moctapped",
        "moctappsd",
        "moctappwd",
        "miss",
        "missctapp",
    ]

    if pk not in available_courts:
        raise Http404(
            "Court pages only implemented for Tennessee Worker Comp Courts, "
            "Maine SJC, Missouri Supreme Court, Missouri Court of Appeals, "
            "Mississippi Supreme Court and Mississippi Court of Appeals."
        )
    # Validate the user has permission
    user = await request.auser()
    if not user.is_staff and not user.is_superuser:  # type: ignore[union-attr]
        if not await user.groups.filter(  # type: ignore
            name__in=[f"uploaders_{pk}"]
        ).aexists():
            raise PermissionDenied(
                "You do not have permission to access this page."
            )

    # Fix mypy errors
    upload_form: Any

    upload_form_classes = {
        "tennworkcompcl": TennWorkCompClUploadForm,
        "tennworkcompapp": TennWorkCompAppUploadForm,
        "me": MeCourtUploadForm,
        "mo": MoCourtUploadForm,
        "moctapped": MoCourtUploadForm,
        "moctappsd": MoCourtUploadForm,
        "moctappwd": MoCourtUploadForm,
        "miss": MissCourtUploadForm,
        "missctapp": MissCourtUploadForm,
    }

    court_seal = seal(pk, ImageSizes.SMALL)
    if "moctapp" in pk:
        # return mo seal
        court_seal = seal("mo", ImageSizes.SMALL)
    if "tennworkcomp" in pk:
        # return tenn seal
        court_seal = seal("tenn", ImageSizes.SMALL)

    upload_form = upload_form_classes[pk]
    form = await sync_to_async(upload_form)(pk=pk)
    if request.method == "POST":
        form = await sync_to_async(upload_form)(
            request.POST, request.FILES, pk=pk
        )
        if await sync_to_async(form.is_valid)():
            cluster = await sync_to_async(form.save)()
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
    return TemplateResponse(
        request,
        "publish.html",
        {
            "court_image": court_seal,
            "form": form,
            "private": True,
            "pk": pk,
        },
    )


async def redirect_og_lookup(request: HttpRequest) -> HttpResponse:
    """Redirect an open graph bot to the page for a RECAP document so that
    it can get good thumbnails and metadata even though it's a PDF.

    If it hits an error, send the bot back to AWS to get the PDF, but set
    "no-og" parameter to be sure the file gets served.
    """
    # Since implementing Ada, the `get_redirect_or_abort` method now returns a
    # valid path for redirection, always prefixed with a slash (/). However,
    # FileField values cannot have a leading slash because it breaks how they
    # interact with MEDIA_ROOT.
    # To ensure compatibility, we're striping the leading slash from the
    # returned redirect path before using it to retrieve the RD record.
    file_path = get_redirect_or_abort(
        request, "file_path", throw_404=True
    ).lstrip("/")
    rd_filter = RECAPDocument.objects.filter(
        filepath_local=file_path
    ).prefetch_related("docket_entry")

    if not await rd_filter.aexists():
        # We couldn't find the URL. Redirect back to AWS, but be sure to serve
        # the file this time. Ideally this doesn't happen, but let's be ready
        # in case it does.
        return HttpResponseRedirect(
            f"https://storage.courtlistener.com/{file_path}?no-og=1"
        )
    else:
        rd = await rd_filter.afirst()
        return await view_recap_document(
            request,
            docket_id=rd.docket_entry.docket_id,
            doc_num=rd.document_number,
            att_num=rd.attachment_number,
            is_og_bot=True,
        )


async def redirect_docket_recap(
    request: HttpRequest,
    court: Court,
    pacer_case_id: str,
) -> HttpResponseRedirect:
    docket: Docket = await aget_object_or_404(
        Docket, pacer_case_id=pacer_case_id, court=court
    )
    return HttpResponseRedirect(
        reverse("view_docket", args=[docket.pk, docket.slug])
    )


async def fetch_docket_entries(docket):
    """Fetch docket entries asociated to docket

    param docket: docket.id to get related docket_entries.
    returns: DocketEntry Queryset.
    """
    de_list = docket.docket_entries.all().prefetch_related(
        Prefetch(
            "recap_documents",
            queryset=RECAPDocument.objects.defer("plain_text"),
        )
    )
    return de_list


async def view_docket(
    request: HttpRequest, pk: int, slug: str
) -> HttpResponse:
    sort_order_asc = True
    form = DocketEntryFilterForm(request.GET, request=request)
    docket, context = await core_docket_data(request, pk)
    await increment_view_count(docket, request)

    de_list = await fetch_docket_entries(docket)

    if await sync_to_async(form.is_valid)():
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
            sort_order_asc = False
            de_list = de_list.order_by(
                "-recap_sequence_number", "-entry_number"
            )

    page = request.GET.get("page", 1)

    @sync_to_async
    def paginate_docket_entries(docket_entries, docket_page):
        paginator = Paginator(docket_entries, 200, orphans=10)
        try:
            return paginator.page(docket_page)
        except PageNotAnInteger:
            return paginator.page(1)
        except EmptyPage:
            return paginator.page(paginator.num_pages)

    paginated_entries = await paginate_docket_entries(de_list, page)

    flag_for_prayers = await sync_to_async(waffle.flag_is_active)(
        request, "pray-and-pay"
    )
    if flag_for_prayers:
        # Extract recap documents from the current page.
        recap_documents = [
            rd
            for entry in await sync_to_async(list)(paginated_entries)
            async for rd in entry.recap_documents.all()
        ]
        # Get prayer counts in bulk.
        prayer_counts = await get_prayer_counts_in_bulk(recap_documents)
        existing_prayers = {}

        if request.user.is_authenticated:
            # Check prayer existence in bulk.
            existing_prayers = await get_existing_prayers_in_bulk(
                request.user, recap_documents
            )

        # Merge counts and existing prayer status to RECAPDocuments.
        for rd in recap_documents:
            rd.prayer_count = prayer_counts.get(rd.id, 0)
            rd.prayer_exists = existing_prayers.get(rd.id, False)

    context.update(
        {
            "parties": await docket.parties.aexists(),
            # Needed to show/hide parties tab.
            "authorities": await docket.ahas_authorities(),
            "docket_entries": paginated_entries,
            "sort_order_asc": sort_order_asc,
            "form": form,
            "get_string": make_get_string(request),
        }
    )
    return TemplateResponse(request, "docket.html", context)


@cache_page_ignore_params(300)
async def view_docket_feed(
    request: HttpRequest, docket_id: int
) -> HttpResponse:
    return await sync_to_async(DocketFeed())(request, docket_id=docket_id)


async def view_parties(
    request: HttpRequest,
    docket_id: int,
    slug: str,
) -> HttpResponse:
    """Show the parties and attorneys tab on the docket with pagination."""

    page = request.GET.get("page", 1)
    docket, context = await core_docket_data(request, docket_id)
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

    @sync_to_async
    def paginate_parties(party_queryset, parties_page):
        paginator = Paginator(party_queryset, 1000)
        try:
            return paginator.page(parties_page)
        except PageNotAnInteger:
            return paginator.page(1)
        except EmptyPage:
            return paginator.page(paginator.num_pages)

    party_types_paginator = await paginate_parties(party_types, page)
    parties: Dict[str, list] = {}
    async for party_type in party_types_paginator.object_list:
        if party_type.name not in parties:
            parties[party_type.name] = []
        parties[party_type.name].append(party_type)

    context.update(
        {
            "parties": parties,
            "parties_paginator": party_types_paginator,
            "docket_entries": await docket.docket_entries.aexists(),
        }
    )
    return TemplateResponse(request, "docket_parties.html", context)


async def docket_idb_data(
    request: HttpRequest,
    docket_id: int,
    slug: str,
) -> HttpResponse:
    docket, context = await core_docket_data(request, docket_id)
    try:
        idb_data = await FjcIntegratedDatabase.objects.aget(
            pk=docket.idb_data_id
        )
    except ObjectDoesNotExist:
        raise Http404("No IDB data for this docket at this time")
    context.update(
        {
            # Needed to show/hide parties tab.
            "parties": await docket.parties.aexists(),
            "docket_entries": await docket.docket_entries.aexists(),
            "origin_csv": choices_to_csv(idb_data, "origin"),
            "jurisdiction_csv": choices_to_csv(idb_data, "jurisdiction"),
            "arbitration_csv": choices_to_csv(
                idb_data, "arbitration_at_filing"
            ),
            "class_action_csv": choices_to_csv(
                idb_data, "termination_class_action_status"
            ),
            "procedural_progress_csv": choices_to_csv(
                idb_data, "procedural_progress"
            ),
            "disposition_csv": choices_to_csv(idb_data, "disposition"),
            "nature_of_judgment_csv": choices_to_csv(
                idb_data, "nature_of_judgement"
            ),
            "judgment_csv": choices_to_csv(idb_data, "judgment"),
            "pro_se_csv": choices_to_csv(idb_data, "pro_se"),
        }
    )
    return TemplateResponse(request, "docket_idb_data.html", context)


async def docket_authorities(
    request: HttpRequest,
    docket_id: int,
    slug: str,
) -> HttpResponse:
    docket, context = await core_docket_data(request, docket_id)
    if not await docket.ahas_authorities():
        raise Http404("No authorities data for this docket at this time")

    context.update(
        {
            # Needed to show/hide parties tab.
            "parties": await docket.parties.aexists(),
            "docket_entries": await docket.docket_entries.aexists(),
            "authorities": docket.authorities_with_data,
        }
    )
    return TemplateResponse(request, "docket_authorities.html", context)


async def make_rd_title(rd: RECAPDocument) -> str:
    de = await DocketEntry.objects.aget(id=rd.docket_entry_id)
    d = await Docket.objects.aget(id=de.docket_id)
    court = await Court.objects.aget(id=d.court_id)
    return "{desc}#{doc_num}{att_num} in {case_name} ({court}{docket_number})".format(
        desc=f"{rd.description} &ndash; " if rd.description else "",
        doc_num=rd.document_number,
        att_num=(
            f", Att. #{rd.attachment_number}"
            if rd.document_type == RECAPDocument.ATTACHMENT
            else ""
        ),
        case_name=best_case_name(d),
        court=court.citation_string,
        docket_number=f", {d.docket_number}" if d.docket_number else "",
    )


async def make_thumb_if_needed(
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
        await make_png_thumbnail_for_instance(
            pk=rd.pk,
            klass=RECAPDocument,
            max_dimension=1068,
        )
        await rd.arefresh_from_db()
    return rd


@ratelimiter_all_10_per_h
def download_docket_entries_csv(
    request: HttpRequest, docket_id: int
) -> HttpResponse:
    """Download csv file containing list of DocketEntry for specific Docket"""

    docket, _ = async_to_sync(core_docket_data)(request, docket_id)
    de_list = async_to_sync(fetch_docket_entries)(docket)
    court_id = docket.court_id
    case_name = docket.slug

    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    filename = f"{case_name}.{court_id}.{docket_id}.{date_str}.csv"

    # TODO check if for large files we'll cache or send file by email
    csv_content = generate_docket_entries_csv_data(de_list)
    response: HttpResponse = HttpResponse(csv_content, content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


async def view_recap_document(
    request: HttpRequest,
    docket_id: int | None = None,
    doc_num: int | None = None,
    att_num: int | None = None,
    slug: str = "",
    is_og_bot: bool = False,
) -> HttpResponse:
    """This view can either load an attachment or a regular document,
    depending on the URL pattern that is matched.
    """
    redirect_to_pacer_modal = False
    rd_qs = (
        RECAPDocument.objects.filter(
            docket_entry__docket__id=docket_id,
            document_number=doc_num,
            attachment_number=att_num,
        )
        .order_by("pk")
        .select_related("docket_entry__docket__court")
    )
    if await rd_qs.aexists():
        rd = await rd_qs.afirst()
    else:
        # Unable to find the docket entry the normal way. In appellate courts, this
        # can be because the main document was converted to an attachment, leaving no
        # main document behind. See:
        #
        # https://github.com/freelawproject/courtlistener/pull/2413
        #
        # When this happens, try redirecting to the first attachment for the entry,
        # if it exists.
        if att_num:
            raise Http404("No RECAPDocument matches the given query.")

        # check if the main document was converted to an attachment and
        # if it was, redirect the user to the attachment page
        rd = await RECAPDocument.objects.filter(
            docket_entry__docket__id=docket_id,
            document_number=doc_num,
            attachment_number=1,
        ).afirst()
        if rd:
            # Get the URL to the attachment page and use the querystring
            # if the request included one
            attachment_page = reverse(
                "view_recap_attachment",
                kwargs={
                    "docket_id": docket_id,
                    "doc_num": doc_num,
                    "att_num": 1,
                    "slug": slug,
                },
            )
            if request.GET.urlencode():
                attachment_page += f"?{request.GET.urlencode()}"
            return HttpResponseRedirect(attachment_page)

        raise Http404("No RECAPDocument matches the given query.")

    # Check if the user has requested automatic redirection to the document
    rd_download_redirect = request.GET.get("redirect_to_download", False)
    redirect_or_modal = request.GET.get("redirect_or_modal", False)
    if rd_download_redirect or redirect_or_modal:
        # Check if the document is available from CourtListener and
        # if it is, redirect to the local document
        # if it isn't, if pacer_url is available and
        # rd_download_redirect is True, redirect to PACER. If redirect_or_modal
        # is True set redirect_to_pacer_modal to True to open the modal.
        if rd.is_available:
            return HttpResponseRedirect(rd.filepath_local.url)
        else:
            if rd.pacer_url and rd_download_redirect:
                return HttpResponseRedirect(rd.pacer_url)
            if rd.pacer_url and redirect_or_modal:
                redirect_to_pacer_modal = True

    title = await make_rd_title(rd)
    rd = await make_thumb_if_needed(request, rd)
    try:
        note = await Note.objects.aget(
            recap_doc_id=rd.pk, user=await request.auser()  # type: ignore[attr-defined]
        )
    except (ObjectDoesNotExist, TypeError):
        # Not saved in notes or anonymous user
        note_form = NoteForm(
            initial={
                "recap_doc_id": rd.pk,
                "name": trunc(title, 100, ellipsis="..."),
            }
        )
    else:
        note_form = NoteForm(instance=note)

    # Override the og:url if we're serving a request to an OG crawler bot
    og_file_path_override = f"/{rd.filepath_local}" if is_og_bot else None

    de = await DocketEntry.objects.aget(id=rd.docket_entry_id)
    d = await Docket.objects.aget(id=de.docket_id)

    flag_for_prayers = await sync_to_async(waffle.flag_is_active)(
        request, "pray-and-pay"
    )
    if flag_for_prayers:
        prayer_counts = await get_prayer_counts_in_bulk([rd])
        existing_prayers = {}

        if request.user.is_authenticated:
            # Check prayer existence.
            existing_prayers = await get_existing_prayers_in_bulk(
                request.user, [rd]
            )

        # Merge counts and existing prayer status to RECAPDocuments.
        rd.prayer_count = prayer_counts.get(rd.id, 0)
        rd.prayer_exists = existing_prayers.get(rd.id, False)

    return TemplateResponse(
        request,
        "recap_document.html",
        {
            "rd": rd,
            "title": title,
            "og_file_path": og_file_path_override,
            "note_form": note_form,
            "private": True,  # Always True for RECAP docs.
            "timezone": COURT_TIMEZONES.get(d.court_id, "US/Eastern"),
            "redirect_to_pacer_modal": redirect_to_pacer_modal,
            "authorities": await rd.cited_opinions.aexists(),
        },
    )


async def view_recap_authorities(
    request: HttpRequest,
    docket_id: int | None = None,
    doc_num: int | None = None,
    att_num: int | None = None,
    slug: str = "",
    is_og_bot: bool = False,
) -> HttpResponse:
    """This view can display authorities of an attachment or a regular
    document, depending on the URL pattern that is matched.
    """
    rd = (
        await RECAPDocument.objects.filter(
            docket_entry__docket__id=docket_id,
            document_number=doc_num,
            attachment_number=att_num,
        )
        .order_by("pk")
        .afirst()
    )
    title = await make_rd_title(rd)
    rd = await make_thumb_if_needed(request, rd)

    try:
        note = await Note.objects.aget(
            recap_doc_id=rd.pk, user=await request.auser()  # type: ignore[attr-defined]
        )
    except (ObjectDoesNotExist, TypeError):
        # Not saved in notes or anonymous user
        note_form = NoteForm(
            initial={
                "recap_doc_id": rd.pk,
                "name": trunc(title, 100, ellipsis="..."),
            }
        )
    else:
        note_form = NoteForm(instance=note)

    # Override the og:url if we're serving a request to an OG crawler bot
    og_file_path_override = f"/{rd.filepath_local}" if is_og_bot else None
    de = await DocketEntry.objects.aget(id=rd.docket_entry_id)
    d = await Docket.objects.aget(id=de.docket_id)
    return TemplateResponse(
        request,
        "recap_authorities.html",
        {
            "rd": rd,
            "title": title,
            "og_file_path": og_file_path_override,
            "note_form": note_form,
            "private": True,  # Always True for RECAP docs.
            "timezone": COURT_TIMEZONES.get(d.court_id, "US/Eastern"),
            "authorities": rd.authorities_with_data,
        },
    )


@never_cache
async def view_opinion_old(
    request: HttpRequest, pk: int, _: str
) -> HttpResponse:
    """Using the cluster ID, return the cluster of opinions.

    We also test if the cluster ID has a user note, and send data
    if needed. If it's a note, we send the bound form for the note so
    it can populate the form on the page. If it has note a note, we send the
    unbound form.
    """
    # Look up the court, cluster, title and note information
    cluster: OpinionCluster = await aget_object_or_404(
        OpinionCluster.objects.prefetch_related(
            Prefetch(
                "sub_opinions",
                queryset=Opinion.objects.order_by("ordering_key"),
            )
        ),
        pk=pk,
    )
    title = ", ".join(
        [
            s
            for s in [
                trunc(best_case_name(cluster), 100, ellipsis="..."),
                await cluster.acitation_string(),
            ]
            if s.strip()
        ]
    )
    has_downloads = False
    async for sub_opinion in cluster.sub_opinions.all():
        if sub_opinion.local_path or sub_opinion.download_url:
            has_downloads = True
            break
    get_string = make_get_string(request)

    try:
        note = await Note.objects.aget(
            cluster_id=cluster.pk,
            user=await request.auser(),  # type: ignore[attr-defined]
            # type: ignore[attr-defined]
        )
    except (ObjectDoesNotExist, TypeError):
        # Not note or anonymous user
        note_form = NoteForm(
            initial={
                "cluster_id": cluster.pk,
                "name": trunc(best_case_name(cluster), 100, ellipsis="..."),
            }
        )
    else:
        note_form = NoteForm(instance=note)

    queries_timeout = False
    results = await es_get_citing_and_related_clusters_with_cache(
        cluster, request
    )
    related_clusters = results.related_clusters
    sub_opinion_ids = results.sub_opinion_pks
    related_search_params = results.url_search_params
    citing_clusters = results.citing_clusters
    citing_cluster_count = results.citing_cluster_count
    queries_timeout = results.timeout

    get_parenthetical_groups = await get_or_create_parenthetical_groups(
        cluster,
    )
    parenthetical_groups = get_parenthetical_groups.prefetch_related(
        "representative",
    )[:3]

    # Identify opinions updated/added in partnership with v|lex for 3 years
    three_years_ago = (
        datetime.datetime.now() - timedelta(days=3 * 365)
    ).date()
    date_created = cluster.date_created.date()
    sponsored = (
        datetime.datetime(2022, 6, 1).date()
        <= date_created
        <= datetime.datetime(2024, 1, 31).date()
        and date_created > three_years_ago
    )

    view_authorities_url = reverse(
        "view_case_authorities", args=[cluster.pk, cluster.slug]
    )
    authorities_context: AuthoritiesContext = AuthoritiesContext(
        citation_record=cluster,
        query_string=request.META["QUERY_STRING"],
        total_authorities_count=await cluster.aauthority_count(),
        view_all_url=view_authorities_url,
        doc_type="opinion",
    )
    await authorities_context.post_init()

    return TemplateResponse(
        request,
        "opinion.html",
        {
            "title": title,
            "caption": await cluster.acaption(),
            "cluster": cluster,
            "has_downloads": has_downloads,
            "note_form": note_form,
            "get_string": get_string,
            "private": cluster.blocked,
            "citing_clusters": citing_clusters,
            "citing_cluster_count": citing_cluster_count,
            "authorities_context": authorities_context,
            "top_parenthetical_groups": parenthetical_groups,
            "summaries_count": await cluster.parentheticals.acount(),
            "sub_opinion_ids": sub_opinion_ids,
            "related_algorithm": "mlt",
            "related_clusters": related_clusters,
            "related_cluster_ids": [
                item["cluster_id"] for item in related_clusters
            ],
            "related_search_params": f"&{urlencode(related_search_params)}",
            "sponsored": sponsored,
            "queries_timeout": queries_timeout,
        },
    )


async def setup_opinion_context(
    cluster: OpinionCluster, request: HttpRequest, tab: str
) -> dict[str, Any]:
    """Generate the basic page information we need to load the page

    :param cluster: The opinion cluster
    :param request: The HTTP request from the user
    :param tab: The tab to load
    :return: The opinion page context used to generate the page
    """
    tab_intros = {
        "authorities": "Authorities for ",
        "cited-by": "Citations to ",
        "related-cases": "Similar cases to ",
        "summaries": "Summaries of ",
        "pdf": "Download PDF for ",
    }
    tab_intro = tab_intros.get(tab, "")
    title = f"{tab_intro}{trunc(best_case_name(cluster), 100, ellipsis='...')}"
    has_downloads = False
    pdf_path = None
    if cluster.filepath_pdf_harvard:
        has_downloads = True
        pdf_path = cluster.filepath_pdf_harvard
    else:
        async for sub_opinion in cluster.sub_opinions.all():
            if str(sub_opinion.local_path).endswith(".pdf"):
                has_downloads = True
                pdf_path = sub_opinion.local_path.url
                break
            elif sub_opinion.download_url:
                has_downloads = True
                pdf_path = None

    get_string = make_get_string(request)

    sub_opinion_pks = [
        str(opinion.pk) async for opinion in cluster.sub_opinions.all()
    ]

    es_has_cited_opinions = await es_cited_case_count(
        cluster.id, sub_opinion_pks
    )
    es_has_related_opinions = await es_related_case_count(
        cluster.id, sub_opinion_pks
    )

    try:
        note = await Note.objects.aget(
            cluster_id=cluster.pk,
            user=await request.auser(),  # type: ignore[attr-defined]
            # type: ignore[attr-defined]
        )
    except (ObjectDoesNotExist, TypeError):
        # Not note or anonymous user
        note_form = NoteForm(
            initial={
                "cluster_id": cluster.pk,
                "name": trunc(best_case_name(cluster), 100, ellipsis="..."),
            }
        )
    else:
        note_form = NoteForm(instance=note)

    # Identify opinions updated/added in partnership with v|lex for 3 years
    three_years_ago = (
        datetime.datetime.now() - timedelta(days=3 * 365)
    ).date()
    date_created = cluster.date_created.date()
    sponsored = (
        datetime.datetime(2022, 6, 1).date()
        <= date_created
        <= datetime.datetime(2024, 1, 31).date()
        and date_created > three_years_ago
    )

    context = {
        "tab": tab,
        "title": title,
        "caption": await cluster.acaption(),
        "cluster": cluster,
        "has_downloads": has_downloads,
        "pdf_path": pdf_path,
        "note_form": note_form,
        "get_string": get_string,
        "private": cluster.blocked,
        "sponsored": sponsored,
        "summaries_count": await cluster.parentheticals.acount(),
        "authorities_count": await cluster.aauthority_count(),
        "related_cases_count": es_has_related_opinions,
        "cited_by_count": es_has_cited_opinions,
    }

    return context


async def get_opinions_base_queryset() -> QuerySet:
    return OpinionCluster.objects.prefetch_related(
        "sub_opinions__opinions_cited", "citations"
    ).select_related("docket__court")


async def render_opinion_view(
    request: HttpRequest,
    cluster: OpinionCluster,
    tab: str,
    additional_context: dict = {},
) -> HttpResponse:
    """Helper function to render opinion views with common context.

    :param request: The HttpRequest object
    :param pk: The primary key for the OpinionCluster
    :param tab: The selected tab
    :param additional_context: Any additional context to be passed to the view
    :return: HttpResponse
    """
    ui_flag_for_o = await sync_to_async(waffle.flag_is_active)(
        request, "ui_flag_for_o"
    )

    if not any([ui_flag_for_o]):
        return await view_opinion_old(request, cluster.pk, "str")

    context = await setup_opinion_context(cluster, request, tab=tab)

    if additional_context:
        context.update(additional_context)

    # Just redirect if people attempt to URL hack to pages without content
    tab_count_mapping = {
        "pdf": "has_downloads",
        "authorities": "authorities_count",
        "cited-by": "cited_by_count",
        "related-by": "related_by_count",
        "summaries": "summaries_count",
    }

    # Check if the current tab needs a redirect based on the mapping
    if context["tab"] in tab_count_mapping:
        count_key = tab_count_mapping[context["tab"]]
        if not context[count_key]:
            return HttpResponseRedirect(
                reverse("view_case", args=[cluster.pk, cluster.slug])
            )

    return TemplateResponse(
        request,
        "opinions.html",
        context,
    )


async def view_summaries(
    request: HttpRequest, pk: int, slug: str
) -> HttpResponse:
    cluster: OpinionCluster = await aget_object_or_404(OpinionCluster, pk=pk)
    parenthetical_groups_qs = await get_or_create_parenthetical_groups(cluster)
    parenthetical_groups = [
        parenthetical_group
        async for parenthetical_group in parenthetical_groups_qs.prefetch_related(
            Prefetch(
                "parentheticals",
                queryset=Parenthetical.objects.order_by("-score"),
            ),
            "parentheticals__describing_opinion__cluster__citations",
            "parentheticals__describing_opinion__cluster__docket__court",
            "representative__describing_opinion__cluster__citations",
            "representative__describing_opinion__cluster__docket__court",
        )
    ]

    return TemplateResponse(
        request,
        "opinion_summaries.html",
        {
            "title": await get_case_title(cluster),
            "caption": await cluster.acaption(),
            "cluster": cluster,
            "private": cluster.blocked,
            "parenthetical_groups": parenthetical_groups,
            "summaries_count": await cluster.parentheticals.acount(),
        },
    )


async def view_authorities(
    request: HttpRequest, pk: int, slug: str, doc_type=0
) -> HttpResponse:
    cluster: OpinionCluster = await aget_object_or_404(OpinionCluster, pk=pk)

    return TemplateResponse(
        request,
        "opinion_authorities.html",
        {
            "title": await get_case_title(cluster),
            "caption": await cluster.acaption(),
            "cluster": cluster,
            "private": cluster.blocked
            or await cluster.ahas_private_authority(),
            "authorities_with_data": await cluster.aauthorities_with_data(),
        },
    )


@never_cache
async def view_opinion(request: HttpRequest, pk: int, _: str) -> HttpResponse:
    """View Opinions

    :param request: HTTP request
    :param pk: The cluster PK
    :param _: url slug
    :return: The old or new opinion HTML
    """
    ui_flag_for_o = await sync_to_async(waffle.flag_is_active)(
        request, "ui_flag_for_o"
    )
    if not ui_flag_for_o:
        return await view_opinion_old(request, pk, "str")

    cluster: OpinionCluster = await aget_object_or_404(
        await get_opinions_base_queryset(), pk=pk
    )
    return await render_opinion_view(request, cluster, "opinions")


async def view_opinion_pdf(
    request: HttpRequest, pk: int, _: str
) -> HttpResponse:
    """View Opinion PDF Tab

    :param request: HTTP request
    :param pk: The cluster PK
    :param _: url slug
    :return: Opinion PDF tab
    """
    cluster: OpinionCluster = await aget_object_or_404(
        await get_opinions_base_queryset(), pk=pk
    )
    return await render_opinion_view(request, cluster, "pdf")


async def view_opinion_authorities(
    request: HttpRequest, pk: int, _: str
) -> HttpResponse:
    """View Opinion Table of Authorities

    :param request: HTTP request
    :param pk: The cluster PK
    :param _: url slug
    :return: Table of Authorities tab
    """
    ui_flag_for_o = await sync_to_async(waffle.flag_is_active)(
        request, "ui_flag_for_o"
    )
    if not ui_flag_for_o:
        # Old page to load for people outside the flag
        return await view_authorities(
            request=request, pk=pk, slug="authorities"
        )

    cluster: OpinionCluster = await aget_object_or_404(
        await get_opinions_base_queryset(), pk=pk
    )

    additional_context = {
        "authorities_with_data": await cluster.aauthorities_with_data(),
    }
    return await render_opinion_view(
        request, cluster, "authorities", additional_context
    )


async def view_opinion_cited_by(
    request: HttpRequest, pk: int, _: str
) -> HttpResponse:
    """View Cited By Tab

    :param request: HTTP request
    :param pk: The cluster PK
    :param _: url slug
    :return: Cited By tab
    """
    cluster: OpinionCluster = await aget_object_or_404(
        await get_opinions_base_queryset(), pk=pk
    )
    cited_query = await es_get_cited_clusters_with_cache(cluster, request)
    additional_context = {
        "citing_clusters": cited_query.citing_clusters,
        "citing_cluster_count": cited_query.citing_cluster_count,
    }
    return await render_opinion_view(
        request, cluster, "cited-by", additional_context
    )


async def view_opinion_summaries(
    request: HttpRequest, pk: int, _: str
) -> HttpResponse:
    """View Opinion Summaries tab

    :param request: HTTP request
    :param pk: The cluster PK
    :param _: url slug
    :return: Summaries tab
    """
    ui_flag_for_o = await sync_to_async(waffle.flag_is_active)(
        request, "ui_flag_for_o"
    )
    if not ui_flag_for_o:
        # Old page to load for people outside the flag
        return await view_summaries(request=request, pk=pk, slug="summaries")

    cluster: OpinionCluster = await aget_object_or_404(
        await get_opinions_base_queryset(), pk=pk
    )
    parenthetical_groups_qs = await get_or_create_parenthetical_groups(cluster)
    parenthetical_groups = [
        parenthetical_group
        async for parenthetical_group in parenthetical_groups_qs.prefetch_related(
            Prefetch(
                "parentheticals",
                queryset=Parenthetical.objects.order_by("-score"),
            ),
            "parentheticals__describing_opinion__cluster__citations",
            "parentheticals__describing_opinion__cluster__docket__court",
            "representative__describing_opinion__cluster__citations",
            "representative__describing_opinion__cluster__docket__court",
        )
    ]
    ui_flag_for_o = await sync_to_async(waffle.flag_is_active)(
        request, "ui_flag_for_o"
    )
    if not ui_flag_for_o:
        # Old page to load for people outside the flag
        return await view_summaries(request=request, pk=pk, slug="summaries")
    additional_context = {
        "parenthetical_groups": parenthetical_groups,
        "ui_flag_for_o": ui_flag_for_o,
    }
    return await render_opinion_view(
        request, cluster, "summaries", additional_context
    )


async def view_opinion_related_cases(
    request: HttpRequest, pk: int, _: str
) -> HttpResponse:
    """View Related Cases Tab

    :param request: HTTP request
    :param pk: The cluster PK
    :param _: url slug
    :return: Related Cases tab
    """
    cluster: OpinionCluster = await aget_object_or_404(
        await get_opinions_base_queryset(), pk=pk
    )
    related_cluster_object = await es_get_related_clusters_with_cache(
        cluster, request
    )
    additional_context = {
        "related_algorithm": "mlt",
        "related_clusters": related_cluster_object.related_clusters,
        "sub_opinion_ids": related_cluster_object.sub_opinion_pks,
        "related_search_params": f"&{urlencode(related_cluster_object.url_search_params)}",
        "queries_timeout": related_cluster_object.timeout,
    }
    return await render_opinion_view(
        request, cluster, "related-cases", additional_context
    )


async def cluster_visualizations(
    request: HttpRequest, pk: int, slug: str
) -> HttpResponse:
    cluster: OpinionCluster = await aget_object_or_404(OpinionCluster, pk=pk)
    return TemplateResponse(
        request,
        "opinion_visualizations.html",
        {
            "title": await get_case_title(cluster),
            "caption": await cluster.acaption(),
            "cluster": cluster,
            "private": cluster.blocked
            or await cluster.ahas_private_authority(),
        },
    )


async def throw_404(request: HttpRequest, context: Dict) -> HttpResponse:
    return TemplateResponse(
        request,
        "volumes_for_reporter.html",
        context,
        status=HTTPStatus.NOT_FOUND,
    )


async def get_prev_next_volumes(
    reporter: str, volume: str
) -> tuple[int | None, int | None]:
    """Get the volume before and after the current one.

    :param reporter: The reporter where the volume is found
    :param volume: The volume we're inspecting
    :return Tuple of the volume number we have prior to the selected one, and
    of the volume number after it.
    """
    volumes = [
        vol
        async for vol in Citation.objects.filter(reporter=reporter)
        .annotate(as_integer=Cast("volume", IntegerField()))
        .values_list("as_integer", flat=True)
        .distinct()
        .order_by("as_integer")
    ]
    index = volumes.index(int(volume))
    volume_previous = volumes[index - 1] if index > 0 else None
    volume_next = volumes[index + 1] if index + 1 < len(volumes) else None
    return volume_next, volume_previous


async def reporter_or_volume_handler(
    request: HttpRequest, reporter: str, volume: str | None = None
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
        return await throw_404(
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
        volumes_in_reporter = (
            Citation.objects.filter(reporter=reporter)
            .order_by("reporter", "volume")
            .values_list("volume", flat=True)
            .distinct()
        )

        if not await volumes_in_reporter.aexists():
            return await throw_404(
                request,
                {
                    "no_volumes": True,
                    "reporter": reporter,
                    "volume_names": volume_names,
                    "private": False,
                },
            )

        return TemplateResponse(
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
    cases_in_volume = OpinionCluster.objects.filter(
        citations__reporter=reporter, citations__volume=volume
    ).order_by("date_filed")

    if not await cases_in_volume.aexists():
        return await throw_404(
            request,
            {
                "no_cases": True,
                "reporter": reporter,
                "volume_names": volume_names,
                "volume": volume,
                "private": False,
            },
        )

    volume_next, volume_previous = await get_prev_next_volumes(
        reporter, volume
    )

    page = request.GET.get("page", 1)

    @sync_to_async
    def paginate_volumes(volumes, volume_page):
        paginator = Paginator(volumes, 100, orphans=10)
        try:
            return paginator.page(volume_page)
        except PageNotAnInteger:
            return paginator.page(1)
        except EmptyPage:
            return paginator.page(paginator.num_pages)

    return TemplateResponse(
        request,
        "volumes_for_reporter.html",
        {
            "cases": await paginate_volumes(cases_in_volume, page),
            "reporter": reporter,
            "variation_names": variation_names,
            "volume": volume,
            "volume_names": volume_names,
            "volume_previous": volume_previous,
            "volume_next": volume_next,
            "private": any([case.blocked async for case in cases_in_volume]),
        },
    )


async def make_reporter_dict() -> Dict:
    """Make a dict of reporter names and abbreviations

    The format here is something like:

        {
            "Atlantic Reporter": ['A.', 'A.2d', 'A.3d'],
        }
    """
    reporters_in_db = [
        rep
        async for rep in Citation.objects.order_by("reporter")
        .values_list("reporter", flat=True)
        .distinct()
    ]

    reporters: Union[defaultdict, OrderedDict] = defaultdict(list)
    for name, abbrev_list in NAMES_TO_EDITIONS.items():
        for abbrev in abbrev_list:
            if abbrev in reporters_in_db:
                reporters[name].append(abbrev)
    reporters = OrderedDict(sorted(reporters.items(), key=lambda t: t[0]))
    return reporters


async def citation_handler(
    request: HttpRequest,
    reporter: str,
    volume: str,
    page: str,
) -> HttpResponse:
    """Load the page when somebody looks up a complete citation"""

    citation_str = " ".join([volume, reporter, page])
    clusters, cluster_count = await get_clusters_from_citation_str(
        reporter, volume, page
    )

    # Show the correct page....
    if cluster_count == 0:
        # No results for an otherwise valid citation.
        return TemplateResponse(
            request,
            "citation_redirect_info_page.html",
            {
                "none_found": True,
                "citation_str": citation_str,
                "private": False,
            },
            status=HTTPStatus.NOT_FOUND,
        )

    if cluster_count == 1:
        # Total success. Redirect to correct location.
        clusters_first = await clusters.afirst()
        return HttpResponseRedirect(clusters_first.get_absolute_url())

    if cluster_count > 1:
        # Multiple results. Show them.
        return TemplateResponse(
            request,
            "citation_redirect_info_page.html",
            {
                "too_many": True,
                "citation_str": citation_str,
                "clusters": clusters,
                "private": await clusters.filter(blocked=True).aexists(),
            },
            status=HTTPStatus.MULTIPLE_CHOICES,
        )
    return HttpResponse(status=500)


def make_citation_url_dict(
    reporter: str, volume: str | None, page: str | None
) -> dict[str, str]:
    """Make a dict of the volume/reporter/page, but only if truthy."""
    d = {"reporter": reporter}
    if volume:
        d["volume"] = volume
    if volume and page:
        d["page"] = page
    return d


async def attempt_reporter_variation(
    request: HttpRequest,
    reporter: str,
    volume: str | None,
    page: str | None,
) -> HttpResponse:
    """Try to disambiguate an unknown reporter using the variations dict.

    The variations dict looks like this:

        {
         "A. 2d": ["A.2d"],
         ...
         "P.R.": ["Pen. & W.", "P.R.R.", "P."],
        }

    This means that there can be more than one canonical reporter for a given
    variation. When that happens, we give up. When there's exactly one, we
    redirect to the canonical variation. When there's zero, we give up.

    :param request: The HTTP request
    :param reporter: The reporter string we're trying to look up, e.g., "f-3d"
    :param volume: The volume requested, if provided
    :param page: The page requested, if provided
    """
    possible_canonicals = get_canonicals_from_reporter(reporter)
    if len(possible_canonicals) == 0:
        # Couldn't find it as a variation. Give up.
        return await throw_404(
            request,
            {"no_reporters": True, "reporter": reporter, "private": True},
        )

    elif len(possible_canonicals) == 1:
        # Unambiguous reporter variation. Great. Redirect to the canonical
        # reporter
        return HttpResponseRedirect(
            reverse(
                "citation_redirector",
                kwargs=make_citation_url_dict(
                    possible_canonicals[0], volume, page
                ),
            ),
        )

    elif len(possible_canonicals) > 1:
        # The reporter variation is ambiguous b/c it can refer to more than
        # one reporter. Abort with a 300 status.
        return TemplateResponse(
            request,
            "citation_redirect_info_page.html",
            {
                "too_many_reporter_variations": True,
                "reporter": reporter,
                "possible_canonicals": possible_canonicals,
                "private": True,
            },
            status=HTTPStatus.MULTIPLE_CHOICES,
        )
    else:
        return HttpResponse(status=500)


async def citation_redirector(
    request: HttpRequest,
    reporter: str,
    volume: str | None = None,
    page: str | None = None,
) -> HttpResponse:
    """Take a citation URL and use it to redirect the user to the canonical
    page for that citation.

    This uses the same infrastructure as the thing that identifies citations in
    the text of opinions.
    """
    reporter_slug = slugify(reporter)

    if reporter != reporter_slug:
        # Reporter provided in non-slugified form. Redirect to slugified
        # version.
        return HttpResponseRedirect(
            reverse(
                "citation_redirector",
                kwargs=make_citation_url_dict(
                    reporter_slug,
                    volume,
                    page,
                ),
            ),
        )

    # Look up the slugified reporter to get its proper version (so-2d -> So. 2d)
    proper_reporter = SLUGIFIED_EDITIONS.get(reporter, None)
    if not proper_reporter:
        return await attempt_reporter_variation(
            request, reporter, volume, page
        )

    # We have a reporter (show volumes in it), a volume (show cases in
    # it), or a citation (show matching citation(s))
    if proper_reporter and volume and page:
        return await citation_handler(request, proper_reporter, volume, page)
    elif proper_reporter and volume and page is None:
        return await reporter_or_volume_handler(
            request, proper_reporter, volume
        )
    elif proper_reporter and volume is None and page is None:
        return await reporter_or_volume_handler(request, proper_reporter)
    return HttpResponse(status=500)


@csrf_exempt
async def citation_homepage(request: HttpRequest) -> HttpResponse:
    """Show the citation homepage"""
    if request.method == "POST":
        form = CitationRedirectorForm(request.POST)
        if await sync_to_async(form.is_valid)():
            # Redirect to the page as a GET instead of a POST
            cd = form.cleaned_data
            citations = eyecite.get_citations(
                cd["reporter"], tokenizer=HYPERSCAN_TOKENIZER
            )
            case_law_citations = filter_out_non_case_law_citations(citations)
            if not case_law_citations:
                return TemplateResponse(
                    request,
                    "volumes_for_reporter.html",
                    {"no_citation_found": True, "private": False},
                    status=HTTPStatus.BAD_REQUEST,
                )
            citation_groups = case_law_citations[0].groups
            citation_dict = {
                "reporter": citation_groups.get("reporter"),
                "volume": citation_groups.get("volume", None),
                "page": citation_groups.get("page", None),
            }
            kwargs = make_citation_url_dict(**citation_dict)
            return HttpResponseRedirect(
                reverse("citation_redirector", kwargs=kwargs)
            )
        else:
            # Error in form, somehow.
            return TemplateResponse(
                request,
                "citation_redirect_info_page.html",
                {"show_homepage": True, "form": form, "private": False},
            )

    form = CitationRedirectorForm()
    reporter_dict = await make_reporter_dict()
    return TemplateResponse(
        request,
        "citation_redirect_info_page.html",
        {
            "show_homepage": True,
            "reporter_dict": reporter_dict,
            "form": form,
            "private": False,
        },
    )


@ensure_csrf_cookie
async def block_item(request: HttpRequest) -> HttpResponse:
    """Block an item from search results using AJAX"""
    user = await request.auser()  # type: ignore[attr-defined]
    if is_ajax(request) and user.is_superuser:  # type: ignore[union-attr]
        obj_type = request.POST["type"]
        pk = request.POST["id"]

        if obj_type not in ["docket", "cluster"]:
            return HttpResponseBadRequest(
                "This view can not handle the provided type"
            )

        cluster: OpinionCluster | None = None
        if obj_type == "cluster":
            # Block the cluster
            cluster = await aget_object_or_404(OpinionCluster, pk=pk)
            if cluster is not None:
                cluster.blocked = True
                cluster.date_blocked = now()
                await cluster.asave()

        docket_pk = (
            pk
            if obj_type == "docket"
            else cluster.docket_id if cluster is not None else None
        )
        if not docket_pk:
            return HttpResponse("It worked")

        d: Docket = await aget_object_or_404(Docket, pk=docket_pk)
        d.blocked = True
        d.date_blocked = now()
        await d.asave()

        return HttpResponse("It worked")
    else:
        return HttpResponseNotAllowed(
            permitted_methods=["POST"], content="Not an ajax request"
        )
