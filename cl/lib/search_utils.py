import logging
import pickle
import re
from collections.abc import Callable
from typing import Any, TypedDict
from urllib.parse import parse_qs, urlencode

from asgiref.sync import async_to_sync, sync_to_async
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.paginator import EmptyPage, Page, PageNotAnInteger
from django.http import HttpRequest
from django.http.request import QueryDict
from django_elasticsearch_dsl.search import Search
from eyecite.models import FullCaseCitation
from eyecite.tokenizers import HyperscanTokenizer

from cl.citations.match_citations_queries import es_get_query_citation
from cl.citations.utils import get_citation_depth_between_clusters
from cl.lib.crypto import sha256
from cl.lib.elasticsearch_utils import (
    build_es_main_query,
    compute_lowest_possible_estimate,
    convert_str_date_fields_to_date_objects,
    fetch_es_results,
    get_facet_dict_for_search_query,
    limit_inner_hits,
    merge_courts_from_db,
    merge_unavailable_fields_on_parent_document,
    set_results_highlights,
    simplify_estimated_count,
)
from cl.lib.paginators import ESPaginator
from cl.lib.types import CleanData
from cl.lib.utils import (
    sanitize_unbalanced_parenthesis,
    sanitize_unbalanced_quotes,
)
from cl.search.constants import RELATED_PATTERN
from cl.search.documents import (
    AudioDocument,
    DocketDocument,
    ESRECAPDocument,
    OpinionClusterDocument,
    OpinionDocument,
    ParentheticalGroupDocument,
    PersonDocument,
)
from cl.search.exception import (
    BadProximityQuery,
    DisallowedWildcardPattern,
    UnbalancedParenthesesQuery,
    UnbalancedQuotesQuery,
)
from cl.search.forms import SearchForm, _clean_form
from cl.search.models import (
    SEARCH_TYPES,
    Court,
    OpinionCluster,
    RECAPDocument,
    SearchQuery,
)

HYPERSCAN_TOKENIZER = HyperscanTokenizer(cache_dir=".hyperscan")

logger = logging.getLogger(__name__)


def check_pagination_depth(page_number):
    """Check if the pagination is too deep (indicating a crawler)"""

    if page_number > settings.MAX_SEARCH_PAGINATION_DEPTH:
        logger.warning(
            "Query depth of %s denied access (probably a crawler)",
            page_number,
        )
        raise PermissionDenied


def make_get_string(
    request: HttpRequest,
    nuke_fields: list[str] | None = None,
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
    courts: dict,
    search_form: SearchForm,
) -> tuple[dict[str, list], str, str]:
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
    court_tabs: dict[str, list] = {
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
                result[
                    "citation_depth"
                ] = await get_citation_depth_between_clusters(
                    citing_cluster_pk=result["cluster_id"],
                    cited_cluster_pk=cited_cluster.pk,
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


class CachedESSearchResults(TypedDict):
    results: Page | list
    main_total: int | None
    child_total: int | None


def retrieve_cached_search_results(
    get_params: QueryDict,
) -> tuple[CachedESSearchResults | None, str]:
    """
    Retrieve cached search results based on the GET parameters.

    :param get_params: The GET parameters provided by the user.
    :return: A two-tuple containing either the cached search results and the
    cache key based ona prefix and the get parameters, or None and the cache key
    if no cached results were found.
    """

    params = get_params.copy()
    # If no page is present in the parameters, set it to 1 to generate the same
    # hash for page 1, regardless of whether the page parameter is included.
    # Apply the same to the q parameter when it is not present in params.
    params.setdefault("page", "1")
    params.setdefault("q", "")
    sorted_params = dict(sorted(params.items()))
    key_prefix = "search_results_cache:"
    params_hash = sha256(pickle.dumps(sorted_params))
    cache_key = f"{key_prefix}{params_hash}"
    cached_results = cache.get(cache_key)
    if cached_results:
        return pickle.loads(cached_results), cache_key
    return None, cache_key


def fetch_and_paginate_results(
    get_params: QueryDict,
    search_query: Search,
    child_docs_count_query: Search | None,
    rows_per_page: int = settings.SEARCH_PAGE_SIZE,
    cache_key: str | None = None,
) -> tuple[Page | list, int, bool, int | None, int | None]:
    """Fetch and paginate elasticsearch results.

    :param get_params: The user get params.
    :param search_query: Elasticsearch DSL Search object
    :param child_docs_count_query: The ES DSL Query to perform the count for
    child documents if required, otherwise None.
    :param rows_per_page: Number of records wanted per page
    :param cache_key: The cache key to use.
    :return: A five-tuple: the paginated results, the ES query time, whether
    there was an error, the total number of hits for the main document, and
    the total number of hits for the child document.
    """

    # Run the query and set up pagination
    if cache_key is not None:
        # Check cache for displaying insights on the Home Page.
        results = cache.get(cache_key)
        if results is not None:
            return results, 0, False, None, None

    # Check micro-cache for all other search requests.
    results_dict, micro_cache_key = retrieve_cached_search_results(get_params)
    if results_dict:
        # Return results and counts. Set query time to 1ms.
        return (
            results_dict["results"],
            1,
            False,
            results_dict["main_total"],
            results_dict["child_total"],
        )

    try:
        page = int(get_params.get("page", 1))
    except ValueError:
        page = 1

    # Check pagination depth
    check_pagination_depth(page)

    # Fetch results from ES
    hits, query_time, error, main_total, child_total = fetch_es_results(
        get_params, search_query, child_docs_count_query, page, rows_per_page
    )

    if error:
        return [], query_time, error, main_total, child_total
    paginator = ESPaginator(main_total, hits, rows_per_page)
    try:
        results = paginator.page(page)
    except PageNotAnInteger:
        results = paginator.page(1)
    except EmptyPage:
        results = paginator.page(paginator.num_pages)

    search_type = get_params.get("type", SEARCH_TYPES.OPINION)
    # Set highlights in results.
    convert_str_date_fields_to_date_objects(results, search_type)
    merge_courts_from_db(results, search_type)
    limit_inner_hits(get_params, results, search_type)
    set_results_highlights(results, search_type)
    merge_unavailable_fields_on_parent_document(results, search_type)

    if cache_key is not None:
        # Cache only Page results for displaying insights on the Home Page.
        cache.set(cache_key, results, settings.QUERY_RESULTS_CACHE)
    elif settings.ELASTICSEARCH_MICRO_CACHE_ENABLED:
        # Cache Page results and counts for all other search requests.
        results_dict = {
            "results": results,
            "main_total": main_total,
            "child_total": child_total,
        }
        serialized_data = pickle.dumps(results_dict)
        cache.set(
            micro_cache_key,
            serialized_data,
            settings.SEARCH_RESULTS_MICRO_CACHE,
        )

    return results, query_time, error, main_total, child_total


def remove_missing_citations(
    missing_citations: list[FullCaseCitation], cd: CleanData
) -> tuple[list[str], str]:
    """Removes missing citations from the query and returns the missing
    citations as strings and the modified query.

    :param missing_citations: A list of FullCaseCitation objects representing
    the citations that are missing from the query.
    :param cd: A CleanData object containing the query string.
    :return: A two-tuple containing a list of missing citation strings and the
    suggested query string with missing citations removed.
    """
    missing_citations_str = [
        citation.corrected_citation() for citation in missing_citations
    ]
    query_string = cd["q"]
    for citation in missing_citations_str:
        query_string = query_string.replace(citation, "")
    suggested_query = (
        " ".join(query_string.split()) if missing_citations_str else ""
    )
    return missing_citations_str, suggested_query


def do_es_search(
    get_params: QueryDict,
    rows: int = settings.SEARCH_PAGE_SIZE,
    facet: bool = True,
    cache_key: str | None = None,
    is_csv_export: bool = False,
):
    """Run Elasticsearch searching and filtering and prepare data to display

    :param get_params: The request.GET params sent by user.
    :param rows: The number of Elasticsearch results to request
    :param facet: Whether to complete faceting in the query
    :param cache_key: A cache key with which to save the results. Note that it
    does not do anything clever with the actual query, so if you use this, your
    cache key should *already* have factored in the query. If None, no caching
    is set or used. Results are saved for six hours.
    :param is_csv_export: Indicates if the data being processed is intended for
    an export process.
    :return: A big dict of variables for use in the search results, homepage, or
    other location.
    """
    paged_results = None
    courts = Court.objects.filter(in_use=True)
    query_time: int | None = 0
    total_query_results: int | None = 0
    top_hits_limit: int | None = 5
    document_type = None
    error_message = ""
    suggested_query = ""
    total_child_results: int | None = 0
    related_cluster = None
    cited_cluster = None
    query_citation = None
    facet_fields = []
    missing_citations_str: list[str] = []
    error = True

    search_form = SearchForm(get_params, courts=courts)
    match get_params.get("type", SEARCH_TYPES.OPINION):
        case SEARCH_TYPES.PARENTHETICAL:
            document_type = ParentheticalGroupDocument
        case SEARCH_TYPES.ORAL_ARGUMENT:
            document_type = AudioDocument
        case SEARCH_TYPES.PEOPLE:
            document_type = PersonDocument
        case SEARCH_TYPES.RECAP | SEARCH_TYPES.DOCKETS:
            document_type = DocketDocument
            # Set a different number of results per page for RECAP SEARCH
            rows = (
                settings.RECAP_SEARCH_PAGE_SIZE if not is_csv_export else rows
            )
        case SEARCH_TYPES.OPINION:
            document_type = OpinionClusterDocument

    if search_form.is_valid() and document_type:
        # Copy cleaned_data to preserve the original data when displaying the form
        cd = search_form.cleaned_data.copy()
        try:
            # Create necessary filters to execute ES query
            search_query = document_type.search()

            if cd["type"] in [
                SEARCH_TYPES.OPINION,
                SEARCH_TYPES.RECAP,
                SEARCH_TYPES.DOCKETS,
            ]:
                query_citation, missing_citations = es_get_query_citation(cd)
                if cd["type"] in [
                    SEARCH_TYPES.OPINION,
                ]:
                    missing_citations_str, suggested_query = (
                        remove_missing_citations(missing_citations, cd)
                    )
                    cd["q"] = suggested_query if suggested_query else cd["q"]
            (
                s,
                child_docs_count_query,
                top_hits_limit,
            ) = build_es_main_query(search_query, cd)
            (
                paged_results,
                query_time,
                error,
                total_query_results,
                total_child_results,
            ) = fetch_and_paginate_results(
                get_params,
                s,
                child_docs_count_query,
                rows_per_page=rows,
                cache_key=cache_key,
            )
            cited_cluster = async_to_sync(add_depth_counts)(
                # Also returns cited cluster if found
                search_data=cd,
                search_results=paged_results,
            )
            related_prefix = RELATED_PATTERN.search(cd["q"])
            if related_prefix:
                related_pks = related_prefix.group("pks").split(",")
                related_cluster = OpinionCluster.objects.filter(
                    sub_opinions__pk__in=related_pks
                ).distinct("pk")
        except UnbalancedParenthesesQuery as e:
            error = True
            error_message = "unbalanced_parentheses"
            if e.error_type == UnbalancedParenthesesQuery.QUERY_STRING:
                suggested_query = sanitize_unbalanced_parenthesis(
                    cd.get("q", "")
                )
        except UnbalancedQuotesQuery as e:
            error = True
            error_message = "unbalanced_quotes"
            if e.error_type == UnbalancedParenthesesQuery.QUERY_STRING:
                suggested_query = sanitize_unbalanced_quotes(cd.get("q", ""))
        except BadProximityQuery as e:
            error = True
            error_message = "bad_proximity_token"
            suggested_query = "proximity_filter"
            if e.error_type == UnbalancedParenthesesQuery.QUERY_STRING:
                suggested_query = "proximity_query"
        except DisallowedWildcardPattern:
            error = True
            error_message = "disallowed_wildcard_pattern"
        finally:
            # Make sure to always call the _clean_form method
            search_form = _clean_form(
                get_params, search_form.cleaned_data, courts
            )
            if cd["type"] in [SEARCH_TYPES.OPINION] and facet:
                # If the search query is valid, pass the cleaned data to filter and
                # retrieve the correct number of opinions per status. Otherwise (if
                # the query has errors), just provide a dictionary containing the
                # search type to get the total number of opinions per status
                facet_fields = get_facet_dict_for_search_query(
                    search_query,
                    cd if not error else {"type": cd["type"]},
                    search_form,
                )

    courts, court_count_human, court_count = merge_form_with_courts(
        courts, search_form
    )
    search_summary_str = search_form.as_text(court_count_human)
    search_summary_dict = search_form.as_display_dict(court_count_human)
    results_details = [
        query_time,
        total_query_results,
        top_hits_limit,
        total_child_results,
    ]

    return {
        "results": paged_results,
        "results_details": results_details,
        "search_form": search_form,
        "search_summary_str": search_summary_str,
        "search_summary_dict": search_summary_dict,
        "error": error,
        "courts": courts,
        "court_count_human": court_count_human,
        "court_count": court_count,
        "query_citation": query_citation,
        "cited_cluster": cited_cluster,
        "related_cluster": related_cluster,
        "facet_fields": facet_fields,
        "error_message": error_message,
        "suggested_query": suggested_query,
        "estimated_count_threshold": simplify_estimated_count(
            compute_lowest_possible_estimate(
                settings.ELASTICSEARCH_CARDINALITY_PRECISION
            )
        ),
        "missing_citations": missing_citations_str,
    }


def get_headers_and_transformations_for_search_export(
    type: str,
) -> tuple[list[str], dict[str, Callable[..., Any]] | None]:
    """
    Retrieves CSV headers and data transformation functions for a given search
    type.

    This function determines the appropriate CSV headers and data transformation
    functions based on the specified Elasticsearch search type. It combines
    headers and transformations from relevant document classes to generate a
    comprehensive set for CSV export.

    :param type: The type of Elasticsearch search to be performed. Valid values
        are defined in the `SEARCH_TYPES` enum.
    :return:  A tuple containing:
        - A list of strings representing the CSV headers.
        - A dictionary where keys are field names and values are callable functions
          that define the data transformations.
    """
    match type:
        case SEARCH_TYPES.PEOPLE:
            keys = PersonDocument.get_csv_headers()
            transformations = PersonDocument.get_csv_transformations()
        case SEARCH_TYPES.ORAL_ARGUMENT:
            keys = AudioDocument.get_csv_headers()
            transformations = AudioDocument.get_csv_transformations()
        case SEARCH_TYPES.PARENTHETICAL:
            keys = ParentheticalGroupDocument.get_csv_headers()
            transformations = (
                ParentheticalGroupDocument.get_csv_transformations()
            )
        case SEARCH_TYPES.RECAP | SEARCH_TYPES.DOCKETS:
            keys = (
                DocketDocument.get_csv_headers()
                + ESRECAPDocument.get_csv_headers()
            )
            transformations = (
                DocketDocument.get_csv_transformations()
                | ESRECAPDocument.get_csv_transformations()
            )
        case SEARCH_TYPES.OPINION:
            keys = (
                OpinionClusterDocument.get_csv_headers()
                + OpinionDocument.get_csv_headers()
            )
            transformations = (
                OpinionClusterDocument.get_csv_transformations()
                | OpinionDocument.get_csv_transformations()
            )
        case _:
            return [], None

    return keys, transformations


def fetch_es_results_for_csv(
    queryset: QueryDict, search_type: str
) -> tuple[list[dict[str, Any]], bool]:
    """Retrieves matching results from Elasticsearch and returns them as a list

    This method will flatten nested results (like those returned by opinion and
    recap searches) and limit the number of results in the list to
    `settings.MAX_SEARCH_RESULTS_EXPORTED`.

    :param queryset: The query parameters sent by the user.
    :param search_type: The type of Elasticsearch search to be performed.
    :return: A tuple containing a list of dictionaries, where each dictionary
        represents a single search result and a boolean value indicating
        whether a search error occurred.
    """
    csv_rows: list[dict[str, Any]] = []

    search = do_es_search(
        queryset, rows=settings.MAX_SEARCH_RESULTS_EXPORTED, is_csv_export=True
    )
    if search["error"]:
        return csv_rows, True

    results = search["results"]
    match search_type:
        case SEARCH_TYPES.OPINION | SEARCH_TYPES.RECAP | SEARCH_TYPES.DOCKETS:
            flat_results = []
            for result in results.object_list:
                parent_dict = result.to_dict(skip_empty=False)
                child_docs = parent_dict.get("child_docs")
                if child_docs:
                    flat_results.extend(
                        [
                            doc["_source"].to_dict() | parent_dict
                            for doc in child_docs
                        ]
                    )
                else:
                    flat_results.extend([parent_dict])
        case _:
            flat_results = [
                result.to_dict(skip_empty=False)
                for result in results.object_list
            ]

    return flat_results[: settings.MAX_SEARCH_RESULTS_EXPORTED], False
