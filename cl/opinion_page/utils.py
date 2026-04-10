import csv
import logging
import traceback
from dataclasses import dataclass, field
from io import StringIO

import waffle
from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth.models import AnonymousUser, User
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest
from django.shortcuts import aget_object_or_404  # type: ignore[attr-defined]
from django_elasticsearch_dsl.search import Search
from elasticsearch.exceptions import ApiError, ConnectionTimeout, RequestError
from elasticsearch_dsl import Q

from cl.alerts.models import DocketAlert
from cl.custom_filters.templatetags.extras import citation
from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.favorites.forms import NoteForm
from cl.favorites.models import Note
from cl.lib.bot_detector import is_bot
from cl.lib.elasticsearch_utils import (
    build_cardinality_count,
    build_join_es_filters,
    build_more_like_this_query,
)
from cl.lib.s3_cache import get_s3_cache, make_s3_cache_key
from cl.lib.string_utils import trunc
from cl.lib.types import CleanData
from cl.recap.constants import COURT_TIMEZONES
from cl.search.documents import OpinionClusterDocument
from cl.search.models import (
    PRECEDENTIAL_STATUS,
    SEARCH_TYPES,
    BankruptcyInformation,
    Docket,
    OpinionCluster,
    OriginatingCourtInformation,
)

logger = logging.getLogger(__name__)


def build_docket_metadata(
    docket: Docket, timezone_str: str
) -> list[dict[str, str | bool]]:
    """Build metadata items for the docket page description list.

    Each item is a dict with 'label' and 'value', plus optional 'url',
    'nofollow', and 'is_external' for linked values.
    """
    import pytz
    from django.utils.timezone import localtime

    items: list[dict[str, str | bool]] = []

    if docket.source in docket.RECAP_SOURCES():
        items.append(
            {
                "label": "Last Updated",
                "value": str(
                    localtime(
                        docket.date_modified, pytz.timezone(timezone_str)
                    )
                ),
            }
        )

    if docket.panel_str:
        items.append({"label": "Panel", "value": docket.panel_str})

    if docket.assigned_to:
        items.append(
            {
                "label": "Assigned To",
                "value": docket.assigned_to.name_full,
                "url": docket.assigned_to.get_absolute_url(),
            }
        )
    elif docket.assigned_to_str:
        items.append(
            {
                "label": "Assigned To",
                "value": docket.assigned_to_str,
                "url": f'/?type=r&assigned_to="{docket.assigned_to_str}"',
                "nofollow": True,
            }
        )

    if docket.referred_to:
        items.append(
            {
                "label": "Referred To",
                "value": docket.referred_to.name_full,
                "url": docket.referred_to.get_absolute_url(),
            }
        )
    elif docket.referred_to_str:
        items.append(
            {
                "label": "Referred To",
                "value": docket.referred_to_str,
                "url": f'/?type=r&referred_to="{docket.referred_to_str}"',
                "nofollow": True,
            }
        )

    if docket.date_cert_granted:
        items.append(
            {
                "label": "Date Certiorari Granted",
                "value": str(docket.date_cert_granted),
            }
        )

    if docket.date_cert_denied:
        items.append(
            {
                "label": "Date Certiorari Denied",
                "value": str(docket.date_cert_denied),
            }
        )

    if docket.date_argued:
        items.append(
            {"label": "Date Argued", "value": str(docket.date_argued)}
        )

    items.append({"label": "Citation", "value": citation(docket)})

    if docket.date_reargued:
        items.append(
            {"label": "Date Reargued", "value": str(docket.date_reargued)}
        )

    if docket.date_reargument_denied:
        items.append(
            {
                "label": "Date Reargument Denied",
                "value": str(docket.date_reargument_denied),
            }
        )

    if docket.date_filed:
        items.append({"label": "Date Filed", "value": str(docket.date_filed)})

    if docket.date_terminated:
        items.append(
            {
                "label": "Date Terminated",
                "value": str(docket.date_terminated),
            }
        )

    if docket.date_last_filing:
        items.append(
            {
                "label": "Date of Last Known Filing",
                "value": str(docket.date_last_filing),
            }
        )

    if docket.cause:
        items.append(
            {
                "label": "Cause",
                "value": docket.cause,
                "url": f'/?type=r&cause="{docket.cause}"',
                "nofollow": True,
            }
        )

    if docket.nature_of_suit:
        items.append(
            {
                "label": "Nature of Suit",
                "value": docket.nature_of_suit,
                "url": f'/?type=r&nature_of_suit="{docket.nature_of_suit}"',
                "nofollow": True,
            }
        )

    if docket.jury_demand:
        items.append(
            {
                "label": "Jury Demand",
                "value": docket.jury_demand,
                "url": f'/?type=r&q=juryDemand:"{docket.jury_demand}"',
                "nofollow": True,
            }
        )

    if docket.jurisdiction_type:
        items.append(
            {"label": "Jurisdiction Type", "value": docket.jurisdiction_type}
        )

    if docket.mdl_status:
        items.append({"label": "MDL Status", "value": docket.mdl_status})

    if docket.appellate_fee_status:
        items.append(
            {"label": "Fee Status", "value": docket.appellate_fee_status}
        )

    if docket.appellate_case_type_information:
        items.append(
            {
                "label": "Case Type Information",
                "value": docket.appellate_case_type_information,
            }
        )

    return items


def build_bankruptcy_metadata(
    bankr_info: BankruptcyInformation | None,
) -> list[dict[str, str]]:
    """Build metadata items for the bankruptcy information section."""
    if not bankr_info:
        return []

    items: list[dict[str, str]] = []

    if bankr_info.date_converted:
        items.append(
            {
                "label": "Date Converted",
                "value": bankr_info.date_converted.strftime("%b. %d, %Y"),
            }
        )

    if bankr_info.date_last_to_file_claims:
        items.append(
            {
                "label": "Last Date to File Claims",
                "value": bankr_info.date_last_to_file_claims.strftime(
                    "%b. %d, %Y"
                ),
            }
        )

    if bankr_info.date_last_to_file_govt:
        items.append(
            {
                "label": "Last Date to File Claims (Gov't)",
                "value": bankr_info.date_last_to_file_govt.strftime(
                    "%b. %d, %Y"
                ),
            }
        )

    if bankr_info.date_debtor_dismissed:
        items.append(
            {
                "label": "Date Debtor Dismissed",
                "value": bankr_info.date_debtor_dismissed.strftime(
                    "%b. %d, %Y"
                ),
            }
        )

    if bankr_info.chapter:
        items.append({"label": "Chapter", "value": bankr_info.chapter})

    if bankr_info.trustee_str:
        items.append({"label": "Trustee", "value": bankr_info.trustee_str})

    return items


def build_originating_court_metadata(
    docket: Docket, og_info: OriginatingCourtInformation | None
) -> list[dict[str, str | bool]]:
    """Build metadata items for the originating court information section."""
    if not og_info:
        return []

    items: list[dict[str, str | bool]] = []

    if docket.appeal_from or docket.appeal_from_str:
        appeal_value = ""
        if docket.appeal_from:
            appeal_value = docket.appeal_from.short_name
        elif docket.appeal_from_str:
            appeal_value = docket.appeal_from_str

        if og_info.docket_number:
            if docket.appeal_from:
                appeal_value += f' (<a class="links" href="/?type=r&docket_number={og_info.docket_number}&court={docket.appeal_from.pk}" rel="nofollow" title="Search for this docket number in the RECAP Archive.">{og_info.docket_number}</a>)'
            elif og_info.administrative_link:
                appeal_value += f' (<a class="links-external" href="{og_info.administrative_link}" target="_blank" rel="noreferrer">{og_info.docket_number}</a>)'
            else:
                appeal_value += f" ({og_info.docket_number})"

        items.append(
            {"label": "Appealed From", "value": appeal_value, "safe": True}
        )

    if og_info.court_reporter:
        items.append(
            {"label": "Court Reporter", "value": og_info.court_reporter}
        )

    if og_info.assigned_to:
        items.append(
            {
                "label": "Trial Judge",
                "value": og_info.assigned_to.name_full,
                "url": og_info.assigned_to.get_absolute_url(),
            }
        )
    elif og_info.assigned_to_str:
        items.append(
            {
                "label": "Trial Judge",
                "value": og_info.assigned_to_str,
                "url": f'/?type=r&assigned_to="{og_info.assigned_to_str}"',
                "nofollow": True,
            }
        )

    if og_info.ordering_judge:
        items.append(
            {
                "label": "Ordering Judge",
                "value": og_info.ordering_judge.name_full,
                "url": og_info.ordering_judge.get_absolute_url(),
            }
        )
    elif og_info.ordering_judge_str:
        items.append(
            {
                "label": "Ordering Judge",
                "value": og_info.ordering_judge_str,
                "url": f'/?type=r&assigned_to="{og_info.ordering_judge_str}"',
                "nofollow": True,
            }
        )

    if og_info.date_filed:
        items.append({"label": "Date Filed", "value": str(og_info.date_filed)})

    if og_info.date_judgment:
        items.append(
            {
                "label": "Date Order/Judgment",
                "value": str(og_info.date_judgment),
            }
        )

    if og_info.date_judgment_eod:
        items.append(
            {
                "label": "Date Order/Judgment EOD",
                "value": str(og_info.date_judgment_eod),
            }
        )

    if og_info.date_filed_noa:
        items.append(
            {"label": "Date NOA Filed", "value": str(og_info.date_filed_noa)}
        )

    if og_info.date_received_coa:
        items.append(
            {
                "label": "Date Rec'd COA",
                "value": str(og_info.date_received_coa),
            }
        )

    return items


def build_docket_tabs(
    docket: Docket,
    parties: bool,
    has_idb_data: bool,
    authority_count: int,
) -> list[dict[str, str]]:
    """Build the tab navigation items for the docket page.

    Each item is a dict with 'label', 'url', and 'key'.
    """
    from django.urls import reverse

    tabs = [
        {
            "label": "Docket Entries",
            "url": docket.get_absolute_url(),
            "key": "entries",
        }
    ]

    if parties:
        tabs.append(
            {
                "label": "Parties and Attorneys",
                "url": reverse(
                    "docket_parties",
                    kwargs={
                        "docket_id": docket.pk,
                        "slug": docket.slug,
                    },
                ),
                "key": "parties",
            }
        )

    if has_idb_data:
        tabs.append(
            {
                "label": "FJC Integrated Database",
                "url": reverse(
                    "docket_idb_data",
                    kwargs={
                        "docket_id": docket.pk,
                        "slug": docket.slug,
                    },
                ),
                "key": "idb",
            }
        )

    if authority_count:
        tabs.append(
            {
                "label": "Authorities",
                "url": reverse(
                    "docket_authorities",
                    kwargs={
                        "docket_id": docket.pk,
                        "slug": docket.slug,
                    },
                ),
                "key": "authorities",
            }
        )

    return tabs


async def get_case_title(cluster: OpinionCluster) -> str:
    return f"{trunc(best_case_name(cluster), 100)}, {await cluster.acitation_string()}"


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


async def core_docket_data(
    request: HttpRequest,
    pk: int,
) -> tuple[Docket, dict[str, bool | str | Docket | NoteForm]]:
    """Gather the core data for a docket, party, or IDB page."""
    docket: Docket = await aget_object_or_404(Docket, pk=pk)
    title = make_docket_title(docket)

    try:
        note = await Note.objects.aget(
            docket_id=docket.pk,
            user=await request.auser(),  # type: ignore[attr-defined]
        )
    except (ObjectDoesNotExist, TypeError):
        # Not saved in notes or anonymous user
        note_form = NoteForm(
            initial={
                "docket_id": docket.pk,
                "name": trunc(best_case_name(docket), 100, ellipsis="..."),
            }
        )
    else:
        note_form = NoteForm(instance=note)

    has_alert = await user_has_alert(await request.auser(), docket)  # type: ignore[arg-type]

    return (
        docket,
        {
            "docket": docket,
            "title": title,
            "note_form": note_form,
            "has_alert": has_alert,
            "timezone": COURT_TIMEZONES.get(docket.court_id, "US/Eastern"),
            "private": docket.blocked,
        },
    )


async def user_has_alert(user: AnonymousUser | User, docket: Docket) -> bool:
    has_alert = False
    if user.is_authenticated:
        has_alert = await DocketAlert.objects.filter(
            docket=docket, user=user, alert_type=DocketAlert.SUBSCRIPTION
        ).aexists()
    return has_alert


def generate_docket_entries_csv_data(docket_entries):
    """Get str representing in memory file from docket_entries.

    :param docket_entries: List of DocketEntry that implements CSVExportMixin.
    :returns str with csv in memory content
    """
    output: StringIO = StringIO()
    csvwriter = csv.writer(output, quotechar='"', quoting=csv.QUOTE_ALL)
    columns = []

    columns = docket_entries[0].get_csv_columns(get_column_name=True)
    columns += (
        docket_entries[0]
        .recap_documents.first()
        .get_csv_columns(get_column_name=True)
    )
    csvwriter.writerow(columns)

    for docket_entry in docket_entries:
        for recap_doc in docket_entry.recap_documents.all():
            csvwriter.writerow(
                docket_entry.to_csv_row() + recap_doc.to_csv_row()
            )

    csv_content: str = output.getvalue()
    output.close()
    return csv_content


async def build_cites_clusters_query(
    cluster_search: Search, sub_opinion_pks: list[str]
) -> Search:
    """Build the ES cites clusters query to find clusters citing specific
    sub-opinions.

    :param cluster_search: The Elasticsearch DSL Search object
    :param sub_opinion_pks: A list of ids of sub-opinions to search for in
    the 'cites' field.
    :return: The ES DSL Search object representing the query to find clusters
    citing the specified sub-opinions.
    """
    cites_query = Q(
        "bool",
        filter=[
            Q("match", cluster_child="opinion"),
            Q("terms", **{"cites": sub_opinion_pks}),
        ],
    )
    cluster_cites_query = cluster_search.query(cites_query)
    search_query = (
        cluster_cites_query.sort({"citeCount": {"order": "desc"}})
        .source(
            includes=[
                "absolute_url",
                "caseName",
                "cluster_id",
                "docketNumber",
                "citation",
                "status",
                "dateFiled",
                "court",
            ]
        )
        .extra(size=20, track_total_hits=True)
        .collapse(field="cluster_id")
    )
    return search_query


async def build_related_clusters_query(
    cluster_search: Search,
    sub_opinion_pks: list[str],
) -> Search:
    """Build the ES related clusters query based on sub-opinion IDs.

    :param cluster_search: The Elasticsearch DSL Search object
    :param sub_opinion_pks: A list of IDs representing sub-opinions to be queried.
    :return: The ES DSL Search object representing the query to find the
    related clusters.
    """
    mlt_query = await build_more_like_this_query(sub_opinion_pks)
    parent_filters = await sync_to_async(build_join_es_filters)(
        {"type": SEARCH_TYPES.OPINION, "stat_published": True}
    )
    default_parent_filter = [Q("match", cluster_child="opinion")]
    parent_filters.extend(default_parent_filter)
    main_query = Q(
        "bool",
        filter=default_parent_filter,
        should=mlt_query,
        minimum_should_match=1,
    )

    cluster_related_query = cluster_search.query(main_query)
    search_query = (
        cluster_related_query.sort({"_score": {"order": "desc"}})
        .source(
            includes=[
                "absolute_url",
                "caseName",
                "cluster_id",
                "docketNumber",
                "citation",
                "status",
                "dateFiled",
                "court",
            ]
        )
        .extra(size=20)
        .collapse(field="cluster_id")
    )
    return search_query


@dataclass
class RelatedCitingResults:
    related_clusters: list[OpinionClusterDocument] = field(
        default_factory=list
    )
    sub_opinion_pks: list[int] = field(default_factory=list)
    url_search_params: dict[str, str] = field(default_factory=dict)
    citing_clusters: list[OpinionClusterDocument] = field(default_factory=list)
    citing_cluster_count: int = 0
    timeout: bool = False


@dataclass
class RelatedClusterResults:
    related_clusters: list[OpinionClusterDocument] = field(
        default_factory=list
    )
    sub_opinion_pks: list[int] = field(default_factory=list)
    url_search_params: dict[str, str] = field(default_factory=dict)
    timeout: bool = False


async def es_get_related_clusters_with_cache(
    cluster: OpinionCluster,
    request: HttpRequest,
) -> RelatedClusterResults:
    """Elastic Related Clusters Search or Cache

    :param cluster:The cluster to use
    :param request:The user request
    :return:Related Cluster Data
    """
    cache = await sync_to_async(get_s3_cache)("db_cache")
    mlt_cache_key = await sync_to_async(make_s3_cache_key)(
        f"clusters-mlt-es:{cluster.pk}", settings.RELATED_CACHE_TIMEOUT
    )
    # By default, all statuses are included. Retrieve the PRECEDENTIAL_STATUS
    # attributes (since they're indexed in ES) instead of the NAMES values.
    search_params: CleanData = {}
    url_search_params = {
        f"stat_{v[0]}": "on" for v in PRECEDENTIAL_STATUS.NAMES
    }
    sub_opinion_pks = [
        str(pk)
        async for pk in cluster.sub_opinions.values_list("pk", flat=True)
    ]
    if settings.RELATED_FILTER_BY_STATUS:
        # Filter results by status (e.g., Precedential)
        # Update URL parameters accordingly
        search_params[
            f"stat_{PRECEDENTIAL_STATUS.get_status_value(settings.RELATED_FILTER_BY_STATUS)}"
        ] = True
        url_search_params = {
            f"stat_{PRECEDENTIAL_STATUS.get_status_value(settings.RELATED_FILTER_BY_STATUS)}": "on"
        }

    related_cluster_result = RelatedClusterResults(
        url_search_params=url_search_params
    )

    if is_bot(request) or not sub_opinion_pks:
        return related_cluster_result

    if not await sync_to_async(waffle.flag_is_active)(
        request, "citing_and_related_enabled"
    ):
        # Don't perform any queries if citing_and_related_enabled is disabled.
        # Return True for timeout to display buttons for users to click.
        return RelatedClusterResults(
            url_search_params=url_search_params, timeout=True
        )

    cached_related_clusters, timeout_related = (
        await cache.aget(mlt_cache_key) or (None, False)
        if settings.RELATED_USE_CACHE
        else (None, False)
    )

    # Prepare related cluster query if not cached results.
    cluster_search = OpinionClusterDocument.search()

    if cached_related_clusters is not None:
        related_cluster_result.related_clusters = cached_related_clusters
        related_cluster_result.timeout = timeout_related
        related_cluster_result.sub_opinion_pks = list(
            map(int, sub_opinion_pks)
        )
        related_cluster_result.url_search_params = url_search_params
        return related_cluster_result

    related_query = await build_related_clusters_query(
        cluster_search, sub_opinion_pks
    )

    related_query = related_query.params(
        timeout=f"{settings.ELASTICSEARCH_FAST_QUERIES_TIMEOUT}s"
    )
    related_query = related_query.extra(
        size=settings.RELATED_COUNT, track_total_hits=False
    )
    try:
        # Execute the Related Query if needed
        response = related_query.execute()
        timeout_related = False
    except (ConnectionError, RequestError, ApiError) as e:
        logger.warning("Error getting cited and related clusters: %s", e)
        if settings.DEBUG is True:
            traceback.print_exc()
        return related_cluster_result
    except ConnectionTimeout as e:
        logger.warning(
            "ConnectionTimeout getting cited and related clusters: %s", e
        )
        response = None
        timeout_related = True

    related_cluster_result.related_clusters = (
        response if response is not None else cached_related_clusters or []
    )
    related_cluster_result.timeout = False
    related_cluster_result.sub_opinion_pks = list(map(int, sub_opinion_pks))

    if not timeout_related:
        await cache.aset(
            mlt_cache_key,
            (related_cluster_result.related_clusters, timeout_related),
            settings.RELATED_CACHE_TIMEOUT,
        )
    return related_cluster_result


async def es_get_cited_clusters_with_cache(
    cluster: OpinionCluster,
    request: HttpRequest,
) -> RelatedCitingResults:
    """Elastic cited by cluster search or cache

    :param cluster:The cluster to check
    :param request:The user request
    :return:The cited by data
    """
    cache = await sync_to_async(get_s3_cache)("db_cache")
    cache_citing_key = await sync_to_async(make_s3_cache_key)(
        f"clusters-cited-es:{cluster.pk}", settings.RELATED_CACHE_TIMEOUT
    )

    sub_opinion_pks = [
        str(pk)
        async for pk in cluster.sub_opinions.values_list("pk", flat=True)
    ]
    cluster_results = RelatedCitingResults()
    if is_bot(request) or not sub_opinion_pks:
        return cluster_results

    if not await sync_to_async(waffle.flag_is_active)(
        request, "citing_and_related_enabled"
    ):
        # Don't perform any queries if citing_and_related_enabled is disabled.
        # Return True for timeout to display buttons for users to click.
        url_search_params = {
            f"stat_{PRECEDENTIAL_STATUS.get_status_value(settings.RELATED_FILTER_BY_STATUS)}": "on"
        }
        return RelatedCitingResults(
            url_search_params=url_search_params, timeout=True
        )

    cached_citing_results, cached_citing_clusters_count, timeout_cited = (
        await cache.aget(cache_citing_key) or (None, False, False)
        if settings.RELATED_USE_CACHE
        else (None, False, False)
    )

    if cached_citing_results is not None:
        cluster_results.citing_clusters = cached_citing_results
        cluster_results.citing_cluster_count = cached_citing_clusters_count
        cluster_results.timeout = timeout_cited
        return cluster_results

    cluster_search = OpinionClusterDocument.search()
    cited_query = await build_cites_clusters_query(
        cluster_search, sub_opinion_pks
    )
    try:
        # Execute the Related Query if needed
        response = cited_query.execute()
        timeout_cited = False
    except (ConnectionError, RequestError, ApiError) as e:
        logger.warning("Error getting cited and related clusters: %s", e)
        if settings.DEBUG is True:
            traceback.print_exc()
        return cluster_results
    except ConnectionTimeout as e:
        logger.warning(
            "ConnectionTimeout getting cited and related clusters: %s", e
        )
        response = None
        timeout_cited = True

    citing_clusters = list(response) if not timeout_cited else []
    cluster_results.citing_clusters = citing_clusters
    cluster_results.citing_cluster_count = (
        response.hits.total.value if response is not None else 0
    )
    cluster_results.timeout = False if citing_clusters else timeout_cited
    if not cluster_results.timeout:
        await cache.aset(
            cache_citing_key,
            (
                cluster_results.citing_clusters,
                cluster_results.citing_cluster_count,
                cluster_results.timeout,
            ),
            settings.RELATED_CACHE_TIMEOUT,
        )
    return cluster_results


async def es_cited_case_count(
    cluster_id: int, sub_opinion_pks: list[str]
) -> int:
    """Elastic quick cited by count query

    :param cluster_id: The cluster id to search with
    :param sub_opinion_pks: The subopinion ids of the cluster
    :return: Opinion Cited Count
    """
    cache = await sync_to_async(get_s3_cache)("db_cache")
    cache_cited_by_key = await sync_to_async(make_s3_cache_key)(
        f"cited-by-count-es:{cluster_id}", settings.RELATED_CACHE_TIMEOUT
    )
    cached_cited_by_count = await cache.aget(cache_cited_by_key) or None
    if cached_cited_by_count is not None:
        return cached_cited_by_count

    cluster_search = OpinionClusterDocument.search()
    cites_query = Q(
        "bool",
        filter=[
            Q("match", cluster_child="opinion"),
            Q("terms", **{"cites": sub_opinion_pks}),
        ],
    )
    cluster_cites_query = cluster_search.query(cites_query)
    cluster_cites_query = build_cardinality_count(
        cluster_cites_query, "cluster_id"
    )
    cited_by_count = (
        cluster_cites_query.execute().aggregations.unique_documents.value
    )

    await cache.aset(
        cache_cited_by_key,
        cited_by_count,
        settings.RELATED_CACHE_TIMEOUT,
    )

    return cited_by_count


async def es_related_case_count(cluster_id, sub_opinion_pks: list[str]) -> int:
    """Elastic quick related cases count

    :param cluster_id: The cluster id of the object
    :param sub_opinion_pks: The sub opinion ids of the cluster
    :return: The count of related cases in elastic
    """

    if not sub_opinion_pks:
        # Early abort if the cluster doesn't have sub opinions. e.g. cluster id: 3561702
        return 0

    cache = await sync_to_async(get_s3_cache)("db_cache")
    cache_related_cases_key = await sync_to_async(make_s3_cache_key)(
        f"related-cases-count-es:{cluster_id}", settings.RELATED_CACHE_TIMEOUT
    )
    cached_related_cases_count = (
        await cache.aget(cache_related_cases_key) or None
    )
    if cached_related_cases_count is not None:
        return cached_related_cases_count

    cluster_search = OpinionClusterDocument.search()
    mlt_query = await build_more_like_this_query(sub_opinion_pks)
    parent_filters = await sync_to_async(build_join_es_filters)(
        {"type": SEARCH_TYPES.OPINION, "stat_published": True}
    )
    default_parent_filter = [Q("match", cluster_child="opinion")]
    parent_filters.extend(default_parent_filter)
    main_query = Q(
        "bool",
        filter=default_parent_filter,
        should=mlt_query,
        minimum_should_match=1,
    )
    cluster_related_query = cluster_search.query(main_query)
    cluster_related_query = build_cardinality_count(
        cluster_related_query, "cluster_id"
    )
    related_cases_count = (
        cluster_related_query.execute().aggregations.unique_documents.value
    )

    await cache.aset(
        cache_related_cases_key,
        related_cases_count,
        settings.RELATED_CACHE_TIMEOUT,
    )

    return related_cases_count
