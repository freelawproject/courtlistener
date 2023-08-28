import logging
import operator
import re
import time
import traceback
from datetime import date
from functools import reduce, wraps
from typing import Any, Callable, Dict, List

from django.conf import settings
from django.core.paginator import Page
from django.http.request import QueryDict
from django_elasticsearch_dsl.search import Search
from elasticsearch.exceptions import RequestError, TransportError
from elasticsearch_dsl import A, Q
from elasticsearch_dsl.connections import connections
from elasticsearch_dsl.query import QueryString, Range
from elasticsearch_dsl.response import Response
from elasticsearch_dsl.utils import AttrDict

from cl.lib.search_utils import BOOSTS, cleanup_main_query
from cl.lib.types import CleanData
from cl.search.constants import (
    ALERTS_HL_TAG,
    SEARCH_ALERTS_ORAL_ARGUMENT_ES_HL_FIELDS,
    SEARCH_HL_TAG,
    SEARCH_ORAL_ARGUMENT_ES_HL_FIELDS,
)
from cl.search.exception import UnbalancedQuery
from cl.search.models import SEARCH_TYPES, Court

logger = logging.getLogger(__name__)

OPENING_CHAR = r"[\(\[]"  # Matches the following characters: (, [
CLOSING_CHAR = r"[\)\]]"  # Matches the following characters: ), ]


def elasticsearch_enabled(func: Callable) -> Callable:
    """A decorator to avoid executing Elasticsearch methods when it's disabled."""

    @wraps(func)
    def wrapper_func(*args, **kwargs) -> Any:
        if not settings.ELASTICSEARCH_DISABLED:
            func(*args, **kwargs)

    return wrapper_func


def check_index(index: str) -> bool:
    """Check if the given index exists

    :param field: elasticsearch index name
    :return: Whether the index exists
    """
    es = connections.get_connection()
    return es.indices.exists(index=index)


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


def make_es_boost_list(fields: Dict[str, float]) -> list[str]:
    """Constructs a list of Elasticsearch fields with their corresponding
    boost values.

    :param fields: A dictionary where keys are field names and values are
    the corresponding boost values.
    :return: A list of Elasticsearch fields with boost values formatted as 'field_name^boost_value'.
    """
    boosted_fields = []
    for k, v in fields.items():
        boosted_fields.append(f"{k}^{v}")
    return boosted_fields


def add_fields_boosting(cd: CleanData) -> list[str]:
    """Applies boosting to specific fields according the search type.

    :param cd: The user input CleanedData
    :return: A list of Elasticsearch fields with their respective boost values.
    """
    # Apply standard qf parameters
    qf = BOOSTS["qf"][cd["type"]].copy()
    if cd["type"] in [SEARCH_TYPES.ORAL_ARGUMENT]:
        # Give a boost on the case_name field if it's obviously a case_name
        # query.
        query = cd.get("q", "")
        vs_query = any(
            [
                " v " in query,
                " v. " in query,
                " vs. " in query,
                " vs " in query,
            ]
        )
        in_re_query = query.lower().startswith("in re ")
        matter_of_query = query.lower().startswith("matter of ")
        ex_parte_query = query.lower().startswith("ex parte ")
        if any([vs_query, in_re_query, matter_of_query, ex_parte_query]):
            qf.update({"caseName": 50})

    return make_es_boost_list(qf)


def check_unbalanced_parenthesis(query: str) -> bool:
    """Check whether the query string has unbalanced opening or closing parentheses.

    :param query: The input query string
    :return: Whether the query is balanced or not.
    """
    opening_count = query.count("(")
    closing_count = query.count(")")

    return opening_count != closing_count


def sanitize_unbalanced_parenthesis(query: str) -> str:
    """Sanitize a query by removing unbalanced opening or closing parentheses.

    :param query: The input query string
    :return: The sanitized query string, after removing unbalanced parentheses.
    """
    opening_count = query.count("(")
    closing_count = query.count(")")
    while opening_count > closing_count:
        # Find last unclosed opening parenthesis position
        last_parenthesis_opened_pos = query.rfind("(")
        # Remove the parenthesis from the query.
        query = (
            query[:last_parenthesis_opened_pos]
            + query[last_parenthesis_opened_pos + 1 :]
        )
        opening_count -= 1

    while closing_count > opening_count:
        # Find last unclosed closing parenthesis position
        last_parenthesis_closed_pos = query.rfind(")")
        # Remove the parenthesis from the query.
        query = (
            query[:last_parenthesis_closed_pos]
            + query[last_parenthesis_closed_pos + 1 :]
        )
        closing_count -= 1

    return query


def append_query_conjunctions(query: str) -> str:
    """Append default AND conjunctions to the query string.
    :param query: The input query string
    :return: The query string with AND conjunctions appended
    """
    words = query.split()
    clean_q: list[str] = []
    inside_group = 0
    quotation = False
    logic_operand = False
    for word in words:
        binary_operator = word.upper() in ["AND", "OR"]
        """
        This variable will be false in the following cases:
            - When the word is a binary operator like AND or OR.
            - When the word is preceded by a logical operator like NOT, AND, OR.
            - When the word is enclosed by (), [] or ""
        """
        should_add_conjunction = clean_q and not any(
            [inside_group, logic_operand, quotation, binary_operator]
        )

        if re.search(OPENING_CHAR, word):
            # Group or range query opened.
            # Increment the depth counter
            inside_group += len(re.findall(OPENING_CHAR, word))
        elif re.search(CLOSING_CHAR, word):
            # Group or range query closed.
            # Decrease the depth counter.
            inside_group -= len(re.findall(CLOSING_CHAR, word))
        elif '"' in word:
            # Quote character found.
            # Flip the quotation flag
            quotation = not quotation

        if should_add_conjunction:
            clean_q.append("AND")
        clean_q.append(word)

        """
        This is computed at the end of each loop, so the method won't
        add conjunctions after logical operators
        """
        logic_operand = word.upper() in ["AND", "OR", "NOT"]

    return " ".join(clean_q)


def build_fulltext_query(fields: list[str], value: str) -> QueryString | List:
    """Given the cleaned data from a form, return a Elastic Search string query or []
    https://www.elastic.co/guide/en/elasticsearch/reference/current/full-text-queries.html

    :param fields: A list of name fields to search in.
    :param value: The string value to search for.
    :return: A Elasticsearch QueryString or [] if the "value" param is empty.
    """
    if value:
        if check_unbalanced_parenthesis(value):
            raise UnbalancedQuery()
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

        # Used for the phrase query_string, no conjunctions appended.
        query_value = cleanup_main_query(value)

        # To enable the search of each term in the query across multiple fields
        # it's necessary to include an "AND" conjunction between each term.
        # https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-query-string-query.html#query-string-multi-field
        # Used for the best_fields query_string.
        query_value_with_conjunctions = append_query_conjunctions(query_value)

        q_should = [
            Q(
                "query_string",
                fields=fields,
                query=query_value_with_conjunctions,
                quote_field_suffix=".exact",
                default_operator="AND",
                tie_breaker=0.3,
            ),
            Q(
                "query_string",
                fields=fields,
                query=query_value,
                quote_field_suffix=".exact",
                default_operator="AND",
                type="phrase",
            ),
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

    if not value:
        return []

    if make_phrase:
        return [Q("match_phrase", **{field: {"query": value, "slop": slop}})]

    if isinstance(value, list):
        value = list(filter(None, value))
        return [Q("terms", **{field: value})]

    return [Q("term", **{field: value})]


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
            "random_ desc": {"random_": {"order": "desc"}},
            "random_ asc": {"random_": {"order": "asc"}},
        }

    else:
        order_by_map = {
            "score desc": {"score": {"order": "desc"}},
            "dateFiled desc": {"dateFiled": {"order": "desc"}},
            "dateFiled asc": {"dateFiled": {"order": "asc"}},
        }

    order_by = cd.get("order_by")
    if order_by and "random_" in order_by:
        # Return random sorting if available.
        # Define the random seed using the value defined in random_{seed}
        seed = int(time.time())
        match = re.search(r"random_(\d+)", order_by)
        if match:
            seed = int(match.group(1))

        order_by_key = re.sub(r"random_\S*", "random_", order_by)
        order = order_by_map[order_by_key]["random_"]["order"]
        random_sort = {
            "_script": {
                "type": "number",
                "script": {
                    "source": "Long.hashCode(doc['id'].value ^ params.seed)",
                    "params": {"seed": seed},
                },
                "order": order,
            }
        }
        return random_sort

    if order_by not in order_by_map:
        # Sort by score in descending order
        return order_by_map["score desc"]

    return order_by_map[order_by]


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
        # Build dateFiled daterange query
        queries_list.extend(
            build_daterange_query(
                "dateFiled",
                cd.get("filed_before", ""),
                cd.get("filed_after", ""),
            )
        )
    if cd["type"] == SEARCH_TYPES.ORAL_ARGUMENT:
        # Build dateArgued daterange query
        queries_list.extend(
            build_daterange_query(
                "dateArgued",
                cd.get("argued_before", ""),
                cd.get("argued_after", ""),
            )
        )
        # Build caseName terms filter
        queries_list.extend(
            build_text_filter("caseName", cd.get("case_name", ""))
        )
        # Build judge terms filter
        queries_list.extend(build_text_filter("judge", cd.get("judge", "")))
    return queries_list


def build_es_base_query(search_query: Search, cd: CleanData) -> Search:
    """Builds filters and fulltext_query based on the given cleaned
     data and returns an elasticsearch query.

    :param search_query: The Elasticsearch search query object.
    :param cd: The cleaned data object containing the query and filters.
    :return:The Elasticsearch search query object.
    """

    string_query = None
    filters = build_es_filters(cd)
    match cd["type"]:
        case SEARCH_TYPES.PARENTHETICAL:
            string_query = build_fulltext_query(
                ["representative_text"], cd.get("q", "")
            )
        case SEARCH_TYPES.ORAL_ARGUMENT:
            fields = [
                "court",
                "court_citation_string",
                "judge",
                "dateArgued_text",
                "dateReargued_text",
                "dateReargumentDenied_text",
                "court_id_text",
                "sha1",
            ]
            fields.extend(add_fields_boosting(cd))
            string_query = build_fulltext_query(
                fields,
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
    return search_query


def build_es_main_query(
    search_query: Search, cd: CleanData
) -> tuple[Search, int, int | None]:
    """Builds and returns an elasticsearch query based on the given cleaned
     data, also performs grouping if required, add highlighting and returns
     additional query related metrics.

    :param search_query: The Elasticsearch search query object.
    :param cd: The cleaned data object containing the query and filters.
    :return: A three tuple, the Elasticsearch search query object after applying
    filters, string query and grouping if needed, the total number of results,
    the total number of top hits returned by a group if applicable.
    """
    search_query = build_es_base_query(search_query, cd)
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


def add_es_highlighting(
    search_query: Search, cd: CleanData, alerts: bool = False
) -> Search:
    """Add elasticsearch highlighting to the search query.

    :param search_query: The Elasticsearch search query object.
    :param cd: The user input CleanedData
    :param alerts: If highlighting is being applied to search Alerts hits.
    :return: The modified Elasticsearch search query object with highlights set
    """

    if cd["type"] == SEARCH_TYPES.ORAL_ARGUMENT:
        highlighting_fields = SEARCH_ORAL_ARGUMENT_ES_HL_FIELDS
        hl_tag = SEARCH_HL_TAG
        if alerts:
            highlighting_fields = SEARCH_ALERTS_ORAL_ARGUMENT_ES_HL_FIELDS
            hl_tag = ALERTS_HL_TAG
        for field in highlighting_fields:
            search_query = search_query.highlight(
                field,
                number_of_fragments=0,
                pre_tags=[f"<{hl_tag}>"],
                post_tags=[f"</{hl_tag}>"],
            )

    return search_query


def merge_highlights_into_result(
    highlights: dict[str, Any], result: AttrDict | dict[str, Any], tag: str
) -> None:
    """Merges the highlight terms into the search result.
    This function processes highlighted fields in the `highlights` attribute
    dictionary, then updates the `result` attribute dictionary with the
    combined highlighted terms.

    :param highlights: The AttrDict object containing highlighted fields and
    their highlighted terms.
    :param result: The AttrDict object containing search results.
    :param tag: The HTML tag used to mark highlighted terms.
    :return: None, the function updates the results in place.
    """

    exact_hl_fields = []
    for (
        field,
        highlight_list,
    ) in highlights.items():
        # If a query highlights fields the "field.exact", "field" or
        # both versions are available. Highlighted terms in each
        # version can differ, so the best thing to do is combine
        # highlighted terms from each version and set it.
        if "exact" in field:
            field = field.split(".exact")[0]
            marked_strings_2 = []
            # Extract all unique marked strings from "field.exact"
            marked_strings_1 = re.findall(
                rf"<{tag}>.*?</{tag}>", highlight_list[0]
            )
            # Extract all unique marked strings from "field" if
            # available
            if field in highlights:
                marked_strings_2 = re.findall(
                    rf"<{tag}>.*?</{tag}>",
                    highlights[field][0],
                )

            unique_marked_strings = list(
                set(marked_strings_1 + marked_strings_2)
            )
            combined_highlights = highlight_list[0]
            for marked_string in unique_marked_strings:
                # Replace unique highlighted terms in a single
                # field.
                unmarked_string = marked_string.replace(
                    f"<{tag}>", ""
                ).replace(f"</{tag}>", "")
                combined_highlights = combined_highlights.replace(
                    unmarked_string, marked_string
                )

            # Remove nested <mark> tags after replace.
            combined_highlights = re.sub(
                rf"<{tag}><{tag}>(.*?)</{tag}></{tag}>",
                rf"<{tag}>\1</{tag}>",
                combined_highlights,
            )

            # Set combined highlighted terms.
            result[field] = combined_highlights
            exact_hl_fields.append(field)

        if field not in exact_hl_fields:
            # If the "field.exact" version has not been set, set
            # the "field" version.
            result[field] = highlight_list[0]


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
                if not hasattr(hit, "highlight"):
                    continue
                highlighted_fields = [
                    k for k in dir(hit.highlight) if not k.startswith("_")
                ]
                for highlighted_field in highlighted_fields:
                    highlight = hit.highlight[highlighted_field][0]
                    hit["_source"][highlighted_field] = highlight
        else:
            if not hasattr(result.meta, "highlight"):
                return

            merge_highlights_into_result(
                result.meta.highlight.to_dict(),
                result,
                SEARCH_HL_TAG,
            )


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
        if response.aggregations:
            response = response.aggregations.groups.buckets
        return response, query_time, error
    except (TransportError, ConnectionError, RequestError) as e:
        logger.warning(f"Error loading search page with request: {get_params}")
        logger.warning(f"Error was: {e}")
        if settings.DEBUG is True:
            traceback.print_exc()
    return [], 0, error


def do_es_podcast_query(
    search_query: Search,
    cd: CleanData,
    rows: int = 20,
) -> Response:
    """Execute an Elasticsearch query for podcasts.

    :param search_query: Elasticsearch DSL Search object
    :param cd: The query CleanedData
    :param rows: Number of rows (items) to be retrieved in the response
    :return: The Elasticsearch DSL response.
    """

    s, total_query_results, top_hits_limit = build_es_main_query(
        search_query, cd
    )
    response = s.extra(from_=0, size=rows).execute()
    return response
