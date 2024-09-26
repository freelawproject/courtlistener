import csv
import logging
import traceback
from dataclasses import dataclass, field
from io import StringIO
from typing import Dict, Tuple, Union

from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth.models import AnonymousUser, User
from django.core.cache import caches
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest
from django.shortcuts import aget_object_or_404  # type: ignore[attr-defined]
from django_elasticsearch_dsl.search import Search
from elasticsearch.exceptions import ApiError, ConnectionTimeout, RequestError
from elasticsearch_dsl import MultiSearch, Q

from cl.alerts.models import DocketAlert
from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.favorites.forms import NoteForm
from cl.favorites.models import Note
from cl.lib.bot_detector import is_bot
from cl.lib.elasticsearch_utils import (
    build_join_es_filters,
    build_more_like_this_query,
)
from cl.lib.string_utils import trunc
from cl.lib.types import CleanData
from cl.recap.constants import COURT_TIMEZONES
from cl.search.documents import OpinionClusterDocument
from cl.search.models import (
    PRECEDENTIAL_STATUS,
    SEARCH_TYPES,
    Docket,
    OpinionCluster,
)

logger = logging.getLogger(__name__)


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
) -> Tuple[Docket, Dict[str, Union[bool, str, Docket, NoteForm]]]:
    """Gather the core data for a docket, party, or IDB page."""
    docket: Docket = await aget_object_or_404(Docket, pk=pk)
    title = make_docket_title(docket)

    try:
        note = await Note.objects.aget(
            docket_id=docket.pk, user=await request.auser()  # type: ignore[attr-defined]
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


async def user_has_alert(
    user: Union[AnonymousUser, User], docket: Docket
) -> bool:
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
        .source(includes=["absolute_url", "caseName", "dateFiled"])
        .extra(size=5, track_total_hits=True)
    )
    return search_query


async def build_related_clusters_query(
    cluster_search: Search,
    sub_opinion_pks: list[str],
    search_params: dict[str, str],
) -> Search:
    """Build the ES related clusters query based on sub-opinion IDs.

    :param cluster_search: The Elasticsearch DSL Search object
    :param sub_opinion_pks: A list of IDs representing sub-opinions to be queried.
    :param search_params: A dict of parameters used to form the query.
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
        .source(includes=["absolute_url", "caseName", "cluster_id"])
        .extra(size=5)
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


async def es_get_citing_and_related_clusters_with_cache(
    cluster: OpinionCluster,
    request: HttpRequest,
) -> RelatedCitingResults:
    """Use Elasticsearch to get clusters citing and related clusters to the
    one we're looking at.

    :param cluster: The cluster we're targeting
    :param request: The HttpRequest object.
    :return: A RelatedCitingResults object containing related_clusters,
    sub_opinion_pks, url_search_params, citing_clusters, citing_cluster_count,
    and a boolean indicating whether the query timed out.
    """

    cache = caches["db_cache"]
    cache_citing_key = f"clusters-cited-es:{cluster.pk}"
    mlt_cache_key = f"clusters-mlt-es:{cluster.pk}"
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

    if is_bot(request) or not sub_opinion_pks:
        return RelatedCitingResults(url_search_params=url_search_params)

    cached_citing_results, cached_citing_cluster_count, timeout_cited = (
        await cache.aget(cache_citing_key) or (None, 0, False)
    )
    cached_related_clusters, timeout_related = (
        await cache.aget(mlt_cache_key) or (None, False)
        if settings.RELATED_USE_CACHE
        else (None, False)
    )
    # Prepare cited and related cluster queries if not cached results.
    cluster_search = OpinionClusterDocument.search()
    multi_search = MultiSearch()
    responses = None
    response_index = 0
    related_index = citing_index = None
    if cached_related_clusters is None:
        related_query = await build_related_clusters_query(
            cluster_search, sub_opinion_pks, search_params
        )
        related_query = related_query.extra(
            size=settings.RELATED_COUNT, track_total_hits=False
        )
        multi_search = multi_search.add(related_query)
        related_index = response_index
        response_index += 1

    if cached_citing_results is None:
        cited_query = await build_cites_clusters_query(
            cluster_search, sub_opinion_pks
        )
        multi_search = multi_search.add(cited_query)
        citing_index = response_index
    try:
        # Execute the MultiSearch request as needed based on available
        # cached results
        multi_search.params(
            timeout=f"{settings.ELASTICSEARCH_FAST_QUERIES_TIMEOUT}s"
        )
        responses = multi_search.execute() if multi_search._searches else []
    except (ConnectionError, RequestError, ApiError) as e:
        logger.warning("Error getting cited and related clusters: %s", e)
        if settings.DEBUG is True:
            traceback.print_exc()
        return RelatedCitingResults(url_search_params=url_search_params)
    except ConnectionTimeout as e:
        logger.warning(
            "ConnectionTimeout getting cited and related clusters: %s", e
        )
        timeout_related = timeout_cited = True

    results = RelatedCitingResults(url_search_params=url_search_params)
    results.related_clusters = (
        list(responses[related_index])
        if responses and related_index is not None
        else cached_related_clusters or []
    )
    results.citing_clusters = (
        list(responses[citing_index])
        if responses and citing_index is not None
        else cached_citing_results or []
    )
    results.citing_cluster_count = (
        responses[citing_index].hits.total.value
        if responses and citing_index is not None
        else cached_citing_cluster_count or 0
    )
    timeout_related = False if results.related_clusters else timeout_related
    timeout_cited = False if results.citing_clusters else timeout_cited

    # Set cache for citing and mlt results.
    if citing_index is not None:
        await cache.aset(
            cache_citing_key,
            (
                results.citing_clusters,
                results.citing_cluster_count,
                timeout_cited,
            ),
            settings.RELATED_CACHE_TIMEOUT,
        )
    if related_index is not None:
        await cache.aset(
            mlt_cache_key,
            (results.related_clusters, timeout_related),
            settings.RELATED_CACHE_TIMEOUT,
        )

    results.timeout = any([timeout_cited, timeout_related])
    results.sub_opinion_pks = list(map(int, sub_opinion_pks))
    return results
