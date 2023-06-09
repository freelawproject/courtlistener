import logging
import operator
import re
import time
import traceback
from datetime import date
from functools import reduce
from typing import Dict, List

from django.conf import settings
from django.core.paginator import Page
from django.http.request import QueryDict
from django_elasticsearch_dsl.search import Search
from elasticsearch.exceptions import RequestError, TransportError
from elasticsearch_dsl import A, Q
from elasticsearch_dsl.query import QueryString, Range
from elasticsearch_dsl.response import Response

from cl.lib.search_utils import cleanup_main_query
from cl.lib.types import CleanData
from cl.search.constants import SEARCH_ORAL_ARGUMENT_HL_FIELDS
from cl.search.models import SEARCH_TYPES, Court

logger = logging.getLogger(__name__)


def build_daterange_query(
    field: str, before: date, after: date, relation: str | None = None
) -> list[Range]:
    """Given field name and date range limits returns ElasticSearch range query or None
    https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-range-query.html#ranges-on-dates

    :param field: elasticsearch index fieldname
    :param before: datetime upper limit
    :param after: datetime lower limit
    :param relation: Indicates how the range query matches values for range fields
    :return: Empty list or list with DSL Range query
    """
    params = {}
    if any([before, after]):
        if hasattr(after, "strftime"):
            params["gte"] = f"{after.isoformat()}T00:00:00Z"
        if hasattr(before, "strftime"):
            params["lte"] = f"{before.isoformat()}T23:59:59Z"
        if relation is not None:
            allowed_relations = ["INTERSECTS", "CONTAINS", "WITHIN"]
            assert (
                relation in allowed_relations
            ), f"'{relation}' is not an allowed relation."
            params["relation"] = relation

    if params:
        return [Q("range", **{field: params})]

    return []


def build_fulltext_query(fields: list[str], value: str) -> QueryString | List:
    """Given the cleaned data from a form, return a Elastic Search string query or []
    https://www.elastic.co/guide/en/elasticsearch/reference/current/full-text-queries.html

    :param fields: A list of name fields to search in.
    :param value: The string value to search for.
    :return: A Elasticsearch QueryString or [] if the "value" param is empty.
    """

    if value:
        value = cleanup_main_query(value)
        # In Elasticsearch, the colon (:) character is used to separate the
        # field name and the field value in a query.
        # To avoid parsing errors escape any colon characters in the value
        # parameter with a backslash.
        if "docketNumber:" in value:
            docket_number_matches = re.findall("docketNumber:([^ ]+)", value)
            for match in docket_number_matches:
                replacement = match.replace(":", r"\:")
                value = value.replace(
                    f"docketNumber:{match}", f"docketNumber:{replacement}"
                )
        q_should = [
            Q(
                "multi_match",
                query=value,
                fields=fields,
                type="phrase",
                operator="AND",
                tie_breaker=0.3,
            ),
            Q("query_string", query=value, default_operator="AND"),
        ]
        return Q("bool", should=q_should)
    return []


def build_term_query(
    field: str, value: str | list, make_phrase: bool = False, slop: int = 0
) -> list:
    """Given field name and value or list of values, return Elasticsearch term
    or terms query or [].
    "term" Returns documents that contain an exact term in a provided field
    NOTE: Use it only whe you want an exact match, avoid using this with text fields
    "terms" Returns documents that contain one or more exact terms in a provided field.

    :param field: elasticsearch index fieldname
    :param value: term or terms to find
    :param make_phrase: Whether we should make a match_phrase query for
    TextField filtering.
    :param slop: Maximum distance between terms in a phrase for a match.
    Only applicable on make_phrase queries.
    :return: Empty list or list with DSL Match query
    """

    if value and make_phrase:
        return [Q("match_phrase", **{field: {"query": value, "slop": slop}})]

    if value and isinstance(value, list):
        value = list(filter(None, value))
        return [Q("terms", **{field: value})]

    if value:
        return [Q("term", **{field: value})]
    return []


def build_text_filter(field: str, value: str) -> List:
    """Given a field and value, return Elasticsearch match_phrase query or [].
    "match_phrase" Returns documents that contain the exact phrase in a
    provided field, by default match_phrase has a slop of 0 that requires all
    terms in the query to appear in the document exactly in the order specified
    NOTE: Use it when you want to match the entire exact phrase, especially in
    text fields where the order of the words matters.
    https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-match-query-phrase.html

    :param field: elasticsearch index field name
    :param value: the phrase to find
    :return: Empty list or list with DSL Phrase query
    """
    if value:
        return [Q("match_phrase", **{field: value})]
    return []


def build_sort_results(cd: CleanData) -> Dict:
    """Given cleaned data, find order_by value and return dict to use with
    ElasticSearch sort

    :param cd: The user input CleanedData
    :return: The short dict.
    """

    if cd["type"] == SEARCH_TYPES.ORAL_ARGUMENT:
        order_by_map = {
            "score desc": {"_score": {"order": "desc"}},
            "dateArgued desc": {"dateArgued": {"order": "desc"}},
            "dateArgued asc": {"dateArgued": {"order": "asc"}},
            "random_123 desc": {"random_123": {"order": "desc"}},
            "random_123 asc": {"random_123": {"order": "asc"}},
        }

    else:
        order_by_map = {
            "score desc": {"score": {"order": "desc"}},
            "dateFiled desc": {"dateFiled": {"order": "desc"}},
            "dateFiled asc": {"dateFiled": {"order": "asc"}},
        }

    order_by = cd.get("order_by")
    if order_by in order_by_map and "random_123" in order_by:
        # Return random sorting if available.
        # Define the random seed using the current timestamp
        seed = int(time.time())
        order = order_by_map[order_by]["random_123"]["order"]
        random_sort = {
            "_script": {
                "type": "number",
                "script": {
                    "source": "Math.random() * params.seed",
                    "params": {"seed": seed},
                },
                "order": order,
            }
        }
        return random_sort

    if order_by and order_by in order_by_map:
        return order_by_map[order_by]

    # Default sort by score in descending order
    return {"score": {"order": "desc"}}


def build_es_filters(cd: CleanData) -> List:
    """Builds elasticsearch filters based on the CleanData object.

    :param cd: An object containing cleaned user data.
    :return: The list of Elasticsearch queries built.
    """

    queries_list = []
    if (
        cd["type"] == SEARCH_TYPES.PARENTHETICAL
        or cd["type"] == SEARCH_TYPES.ORAL_ARGUMENT
    ):
        # Build court terms filter
        queries_list.extend(
            build_term_query(
                "court_id",
                cd.get("court", "").split(),
            )
        )
        # Build docket number term query
        queries_list.extend(
            build_term_query(
                "docketNumber",
                cd.get("docket_number", ""),
                make_phrase=True,
                slop=1,
            )
        )
    if cd["type"] == SEARCH_TYPES.PARENTHETICAL:
        # Build daterange query
        queries_list.extend(
            build_daterange_query(
                "dateFiled",
                cd.get("filed_before", ""),
                cd.get("filed_after", ""),
            )
        )
    if cd["type"] == SEARCH_TYPES.ORAL_ARGUMENT:
        # Build daterange query
        queries_list.extend(
            build_daterange_query(
                "dateArgued",
                cd.get("argued_before", ""),
                cd.get("argued_after", ""),
            )
        )
        # Build court terms filter
        queries_list.extend(
            build_text_filter("caseName", cd.get("case_name", ""))
        )
        # Build court terms filter
        queries_list.extend(build_text_filter("judge", cd.get("judge", "")))
    return queries_list


def build_es_main_query(
    search_query: Search, cd: CleanData
) -> tuple[Search, int, int | None]:
    """Builds and returns an elasticsearch query based on the given cleaned
     data.
    :param search_query: The Elasticsearch search query object.
    :param cd: The cleaned data object containing the query and filters.

    :return: A three tuple, the Elasticsearch search query object after applying
    filters, string query and grouping if needed, the total number of results,
    the total number of top hits returned by a group if applicable.
    """

    string_query = None
    filters = build_es_filters(cd)
    match cd["type"]:
        case SEARCH_TYPES.PARENTHETICAL:
            string_query = build_fulltext_query(
                ["representative_text"], cd.get("q", "")
            )
        case SEARCH_TYPES.ORAL_ARGUMENT:
            string_query = build_fulltext_query(
                [
                    "caseName",
                    "docketNumber",
                    "court",
                    "court_id",
                    "judge",
                    "sha1",
                ],
                cd.get("q", ""),
            )

    if filters or string_query:
        # Apply filters first if there is at least one set.
        if filters:
            search_query = search_query.filter(reduce(operator.iand, filters))
        # Apply string query after if is set, required to properly
        # compute elasticsearch scores.
        if string_query:
            search_query = search_query.query(string_query)
    else:
        search_query = search_query.query("match_all")
    total_query_results = search_query.count()

    # Create groups aggregation if needed.
    top_hits_limit = group_search_results(
        search_query,
        cd,
        build_sort_results(cd),
    )

    search_query = add_es_highlighting(search_query, cd)
    if cd["type"] == SEARCH_TYPES.ORAL_ARGUMENT:
        search_query = search_query.sort(build_sort_results(cd))

    return search_query, total_query_results, top_hits_limit


def add_es_highlighting(search_query: Search, cd: CleanData):
    if cd["type"] == SEARCH_TYPES.ORAL_ARGUMENT:
        highlighting_fields = SEARCH_ORAL_ARGUMENT_HL_FIELDS
        for field in highlighting_fields:
            search_query = search_query.highlight(
                field,
                number_of_fragments=0,
                pre_tags=["<mark>"],
                post_tags=["</mark>"],
            )

    return search_query


def set_results_highlights(results: Page, search_type: str) -> None:
    """Sets the highlights for each search result in a Page object by updating
    related fields in _source dict.

    :param results: The Page object containing search results.
    :param search_type: The search type to perform.
    :return: None, the function updates the results in place.
    """

    for result in results.object_list:
        if search_type == SEARCH_TYPES.PARENTHETICAL:
            top_hits = result.grouped_by_opinion_cluster_id.hits.hits
            for hit in top_hits:
                if hasattr(hit, "highlight"):
                    highlighted_fields = [
                        k for k in dir(hit.highlight) if not k.startswith("_")
                    ]
                    for highlighted_field in highlighted_fields:
                        highlight = hit.highlight[highlighted_field][0]
                        hit["_source"][highlighted_field] = highlight
        else:
            if hasattr(result.meta, "highlight"):
                for (
                    field,
                    highlight_list,
                ) in result.meta.highlight.to_dict().items():
                    result[field] = highlight_list[0]


def group_search_results(
    search: Search,
    cd: CleanData,
    order_by: dict[str, dict[str, str]],
) -> int | None:
    """Group search results by a specified field and return top hits for each
    group.

    :param search: The elasticsearch Search object representing the query.
    :param cd: The cleaned data object containing the query and filters.
    :param order_by: The field name to use for sorting the top hits.
    :return: The top_hits_limit or None.
    """

    top_hits_limit = 5
    if cd["type"] == SEARCH_TYPES.PARENTHETICAL:
        # If cluster_id query set the top_hits_limit to 100
        # Top hits limit in elasticsearch is 100
        cluster_query = re.search(r"cluster_id:\d+", cd["q"])
        size = top_hits_limit if not cluster_query else 100
        group_by = "cluster_id"
        aggregation = A("terms", field=group_by, size=1_000_000)
        sub_aggregation = A(
            "top_hits",
            size=size,
            sort={"_score": {"order": "desc"}},
            highlight={
                "fields": {
                    "representative_text": {},
                    "docketNumber": {},
                },
                "pre_tags": ["<mark>"],
                "post_tags": ["</mark>"],
            },
        )
        aggregation.bucket("grouped_by_opinion_cluster_id", sub_aggregation)

        order_by_field = list(order_by.keys())[0]
        if order_by_field != "score":
            # If order field is other than score (elasticsearch relevance)
            # Add a max aggregation to calculate the max value of the provided
            # field to order, for each bucket.
            max_value_field = A("max", field=order_by_field)
            aggregation.bucket("max_value_field", max_value_field)

            # Add a bucket_sort aggregation to sort the result buckets based on
            # the max_value_field aggregation
            bucket_sort = A(
                "bucket_sort",
                sort=[{"max_value_field": order_by[order_by_field]}],
            )
            aggregation.bucket("sorted_buckets", bucket_sort)
        else:
            # If order field score (elasticsearch relevance)
            # Add a max aggregation to calculate the max value of _score
            max_score = A("max", script="_score")
            aggregation.bucket("max_score", max_score)
            bucket_sort_score = A(
                "bucket_sort", sort=[{"max_score": {"order": "desc"}}]
            )
            aggregation.bucket("sorted_buckets", bucket_sort_score)

        search.aggs.bucket("groups", aggregation)

    return top_hits_limit


def convert_str_date_fields_to_date_objects(
    results: Page, date_field_name: str, search_type: str
) -> None:
    """Converts string date fields in Elasticsearch search results to date
    objects.

    :param results: A Page object containing the search results to be modified.
    :param date_field_name: The date field name containing the date strings
    to be converted.
    :param search_type: The search type to perform.
    :return: None, the function modifies the search results object in place.
    """
    if search_type == SEARCH_TYPES.PARENTHETICAL:
        for result in results.object_list:
            if search_type == SEARCH_TYPES.PARENTHETICAL:
                top_hits = result.grouped_by_opinion_cluster_id.hits.hits
                for hit in top_hits:
                    date_str = hit["_source"][date_field_name]
                    date_obj = date.fromisoformat(date_str)
                    hit["_source"][date_field_name] = date_obj


def merge_courts_from_db(results: Page, search_type: str) -> None:
    """Merges court citation strings from the database into search results.

    :param results: A Page object containing the search results to be modified.
    :param search_type: The search type to perform.
    :return: None, the function modifies the search results object in place.
    """

    if search_type == SEARCH_TYPES.PARENTHETICAL:
        court_ids = [
            d["grouped_by_opinion_cluster_id"]["hits"]["hits"][0]["_source"][
                "court_id"
            ]
            for d in results
        ]
        courts_in_page = Court.objects.filter(pk__in=court_ids).only(
            "pk", "citation_string"
        )
        courts_dict = {}
        for court in courts_in_page:
            courts_dict[court.pk] = court.citation_string

        for result in results.object_list:
            top_hits = result.grouped_by_opinion_cluster_id.hits.hits
            for hit in top_hits:
                court_id = hit["_source"]["court_id"]
                hit["_source"]["citation_string"] = courts_dict.get(court_id)


def fetch_es_results(
    get_params: QueryDict,
    search_query: Search,
    page: int = 1,
    rows_per_page: int = settings.SEARCH_PAGE_SIZE,
) -> tuple[Response | list, int, bool]:
    """Fetch elasticsearch results with pagination.

    :param get_params: The user get params.
    :param search_query: Elasticsearch DSL Search object
    :param page: Current page number
    :param rows_per_page: Number of records wanted per page
    :return: A three tuple, the ES response, the ES query time and if
    there was an error.
    """

    # Compute "from" parameter for Elasticsearch
    es_from = (page - 1) * rows_per_page
    error = True
    try:
        # Execute the Elasticsearch search with "size" and "from" parameters
        response = search_query.extra(
            from_=es_from, size=rows_per_page
        ).execute()
        query_time = response.took
        error = False
        return response, query_time, error
    except (TransportError, ConnectionError, RequestError) as e:
        logger.warning(f"Error loading search page with request: {get_params}")
        logger.warning(f"Error was: {e}")
        if settings.DEBUG is True:
            traceback.print_exc()
    return [], 0, error
