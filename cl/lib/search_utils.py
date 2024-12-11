import re
from typing import Any, Dict, List, Optional, Tuple, cast
from urllib.parse import parse_qs, urlencode

from asgiref.sync import sync_to_async
from django.core.paginator import Page
from django.http import HttpRequest
from eyecite.tokenizers import HyperscanTokenizer

from cl.citations.utils import get_citation_depth_between_clusters
from cl.lib.types import SearchParam
from cl.search.forms import SearchForm
from cl.search.models import (
    SEARCH_TYPES,
    Court,
    OpinionCluster,
    RECAPDocument,
    SearchQuery,
)

HYPERSCAN_TOKENIZER = HyperscanTokenizer(cache_dir=".hyperscan")


def make_get_string(
    request: HttpRequest,
    nuke_fields: Optional[List[str]] = None,
) -> str:
    """Makes a get string from the request object. If necessary, it removes
    the pagination parameters.
    """
    if nuke_fields is None:
        nuke_fields = ["page", "show_alert_modal"]
    get_dict = parse_qs(request.META["QUERY_STRING"])
    for key in nuke_fields:
        try:
            del get_dict[key]
        except KeyError:
            pass
    get_string = urlencode(get_dict, True)
    if len(get_string) > 0:
        get_string += "&"
    return get_string


def merge_form_with_courts(
    courts: Dict,
    search_form: SearchForm,
) -> Tuple[Dict[str, List], str, str]:
    """Merges the courts dict with the values from the search form.

    Final value is like (note that order is significant):
    courts = {
        'federal': [
            {'name': 'Eighth Circuit',
             'id': 'ca8',
             'checked': True,
             'jurisdiction': 'F',
             'has_oral_argument_scraper': True,
            },
            ...
        ],
        'district': [
            {'name': 'D. Delaware',
             'id': 'deld',
             'checked' False,
             'jurisdiction': 'FD',
             'has_oral_argument_scraper': False,
            },
            ...
        ],
        'state': [
            [{}, {}, {}][][]
        ],
        ...
    }

    State courts are a special exception. For layout purposes, they get
    bundled by supreme court and then by hand. Yes, this means new state courts
    requires manual adjustment here.
    """
    # Are any of the checkboxes checked?

    checked_statuses = [
        field.value()
        for field in search_form
        if field.html_name.startswith("court_")
    ]
    no_facets_selected = not any(checked_statuses)
    all_facets_selected = all(checked_statuses)
    court_count = str(
        len([status for status in checked_statuses if status is True])
    )
    court_count_human = court_count
    if all_facets_selected:
        court_count_human = "All"

    for field in search_form:
        if no_facets_selected:
            for court in courts:
                court.checked = True
        else:
            for court in courts:
                # We're merging two lists, so we have to do a nested loop
                # to find the right value.
                if f"court_{court.pk}" == field.html_name:
                    court.checked = field.value()
                    break

    # Build the dict with jurisdiction keys and arrange courts into tabs
    court_tabs: Dict[str, List] = {
        "federal": [],
        "district": [],
        "state": [],
        "special": [],
        "military": [],
        "tribal": [],
    }
    bap_bundle = []
    b_bundle = []
    states = []
    territories = []
    for court in courts:
        if court.jurisdiction == Court.FEDERAL_APPELLATE:
            court_tabs["federal"].append(court)
        elif court.jurisdiction == Court.FEDERAL_DISTRICT:
            court_tabs["district"].append(court)
        elif court.jurisdiction in Court.BANKRUPTCY_JURISDICTIONS:
            # Bankruptcy gets bundled into BAPs and regular courts.
            if court.jurisdiction == Court.FEDERAL_BANKRUPTCY_PANEL:
                bap_bundle.append(court)
            else:
                b_bundle.append(court)
        elif court.jurisdiction in Court.STATE_JURISDICTIONS:
            states.append(court)
        elif court.jurisdiction in Court.TERRITORY_JURISDICTIONS:
            territories.append(court)
        elif court.jurisdiction in [
            Court.FEDERAL_SPECIAL,
            Court.COMMITTEE,
            Court.INTERNATIONAL,
        ]:
            court_tabs["special"].append(court)
        elif court.jurisdiction in Court.MILITARY_JURISDICTIONS:
            court_tabs["military"].append(court)
        elif court.jurisdiction in Court.TRIBAL_JURISDICTIONS:
            court_tabs["tribal"].append(court)

    # Put the bankruptcy bundles in the courts dict
    if bap_bundle:
        court_tabs["bankruptcy_panel"] = [bap_bundle]
    court_tabs["bankruptcy"] = [b_bundle]
    court_tabs["state"] = [states, territories]

    return court_tabs, court_count_human, court_count


async def add_depth_counts(
    search_data: dict[str, Any],
    search_results: Page,
) -> OpinionCluster | None:
    """If the search data contains a single "cites" term (e.g., "cites:(123)"),
    calculate and append the citation depth information between each ES
    result and the cited OpinionCluster. We only do this for *single* "cites"
    terms to avoid the complexity of trying to render multiple depth
    relationships for all the possible result-citation combinations.

    :param search_data: The cleaned search form data
    :param search_results: The paginated ES results
    :return The OpinionCluster if the lookup was successful
    """

    cites_query_matches = re.findall(r"cites:\((\d+)\)", search_data["q"])
    if (
        len(cites_query_matches) == 1
        and search_data["type"] == SEARCH_TYPES.OPINION
    ):
        try:
            cited_cluster = await OpinionCluster.objects.aget(
                sub_opinions__pk=cites_query_matches[0]
            )
        except OpinionCluster.DoesNotExist:
            return None
        else:
            for result in search_results.object_list:
                result["citation_depth"] = (
                    await get_citation_depth_between_clusters(
                        citing_cluster_pk=result["cluster_id"],
                        cited_cluster_pk=cited_cluster.pk,
                    )
                )
            return cited_cluster
    else:
        return None


async def clean_up_recap_document_file(item: RECAPDocument) -> None:
    """Clean up the RecapDocument file-related fields after detecting the file
    doesn't exist in the storage.

    :param item: The RECAPDocument to work on.
    :return: None
    """

    if type(item) == RECAPDocument:
        await sync_to_async(item.filepath_local.delete)()
        item.sha1 = ""
        item.date_upload = None
        item.file_size = None
        item.page_count = None
        item.is_available = False
        await item.asave()


def store_search_query(request: HttpRequest, search_results: dict) -> None:
    """Saves an user's search query in a SearchQuery model

    :param request: the request object
    :param search_results: the dict returned by `do_es_search` function
    :return None
    """
    is_error = search_results.get("error")
    search_query = SearchQuery(
        user=None if request.user.is_anonymous else request.user,
        get_params=request.GET.urlencode(),
        failed=is_error,
        query_time_ms=None,
        hit_cache=False,
        source=SearchQuery.WEBSITE,
        engine=SearchQuery.ELASTICSEARCH,
    )
    if is_error:
        # Leave `query_time_ms` as None if there is an error
        search_query.save()
        return

    search_query.query_time_ms = search_results["results_details"][0]
    # do_es_search returns 1 as query time if the micro cache was hit
    search_query.hit_cache = search_query.query_time_ms == 1

    search_query.save()


def store_search_api_query(
    request: HttpRequest, failed: bool, query_time: int | None, engine: int
) -> None:
    """Store the search query from the Search API.

    :param request: The HTTP request object.
    :param failed: Boolean indicating if the query execution failed.
    :param query_time: The time taken to execute the query in milliseconds or
    None if not applicable.
    :param engine: The search engine used to execute the query.
    :return: None
    """
    SearchQuery.objects.create(
        user=None if request.user.is_anonymous else request.user,
        get_params=request.GET.urlencode(),
        failed=failed,
        query_time_ms=query_time,
        hit_cache=False,
        source=SearchQuery.API,
        engine=engine,
    )
