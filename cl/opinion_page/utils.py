from typing import Dict, Tuple, Union

from asgiref.sync import sync_to_async
from django.contrib.auth.models import AnonymousUser, User
from django.core.cache import caches
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest
from django.shortcuts import aget_object_or_404  # type: ignore[attr-defined]
from elasticsearch_dsl import Q

from cl.alerts.models import DocketAlert
from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.favorites.forms import NoteForm
from cl.favorites.models import Note
from cl.lib.elasticsearch_utils import do_count_query
from cl.lib.string_utils import trunc
from cl.recap.constants import COURT_TIMEZONES
from cl.search.documents import OpinionClusterDocument
from cl.search.models import Docket, OpinionCluster


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
    docket = await aget_object_or_404(Docket, pk=pk)
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

    has_alert = await user_has_alert(await request.auser(), docket)  # type: ignore[attr-defined]

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


async def es_get_citing_clusters_with_cache(
    cluster: OpinionCluster,
) -> tuple[list[OpinionClusterDocument], int | None]:
    """Use Elasticsearch to get clusters citing the one we're looking at

    :param cluster: The cluster we're targeting
    :type cluster: OpinionCluster
    :return: A tuple of the list of ES results and the number of results
    """
    cache_key = f"citing-es:{cluster.pk}"
    cache = caches["db_cache"]
    cached_results = await cache.aget(cache_key)
    if cached_results is not None:
        return cached_results

    # No cached results. Get the citing results from Elasticsearch
    sub_opinion_pks = cluster.sub_opinions.values_list("pk", flat=True)
    ids_str = [str(pk) async for pk in sub_opinion_pks]
    cites_query = Q(
        "bool",
        filter=[
            Q("match", cluster_child="opinion"),
            Q("terms", **{"cites": ids_str}),
        ],
    )
    cluster_document = OpinionClusterDocument.search()
    cluster_cites_query = cluster_document.query(cites_query)
    search_query = (
        cluster_cites_query.sort({"citeCount": {"order": "desc"}})
        .source(includes=["absolute_url", "caseName", "dateFiled"])
        .extra(size=5)
    )
    results = await sync_to_async(search_query.execute)()
    citing_cluster_count = await sync_to_async(do_count_query)(
        cluster_cites_query
    )
    citing_clusters = list(results)
    a_week = 60 * 60 * 24 * 7

    if citing_cluster_count is not None:
        # Cache only if the citing_cluster_count query was successful.
        await cache.aset(
            cache_key, (citing_clusters, citing_cluster_count), a_week
        )
    return citing_clusters, citing_cluster_count
