import logging
import operator
import re
import time
import traceback
from copy import deepcopy
from dataclasses import fields
from datetime import date, datetime
from functools import reduce, wraps
from typing import Any, Callable, Dict, List, Literal

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.cache import caches
from django.core.paginator import EmptyPage, Page
from django.db.models import QuerySet
from django.db.models.functions import Substr
from django.forms.boundfield import BoundField
from django.http import HttpRequest
from django.http.request import QueryDict
from django_elasticsearch_dsl.search import Search
from elasticsearch.exceptions import ApiError, RequestError, TransportError
from elasticsearch_dsl import A, MultiSearch, Q
from elasticsearch_dsl import Search as SearchDSL
from elasticsearch_dsl.query import Query, QueryString, Range
from elasticsearch_dsl.response import Hit, Response
from elasticsearch_dsl.utils import AttrDict

from cl.lib.bot_detector import is_bot
from cl.lib.date_time import midnight_pt
from cl.lib.paginators import ESPaginator
from cl.lib.types import (
    ApiPositionMapping,
    BasePositionMapping,
    CleanData,
    ESRangeQueryParams,
)
from cl.lib.utils import (
    check_for_proximity_tokens,
    check_unbalanced_parenthesis,
    check_unbalanced_quotes,
    cleanup_main_query,
    get_array_of_selected_fields,
    lookup_child_courts,
)
from cl.people_db.models import Position
from cl.search.constants import (
    ALERTS_HL_TAG,
    BOOSTS,
    PEOPLE_ES_HL_FIELDS,
    PEOPLE_ES_HL_KEYWORD_FIELDS,
    RELATED_PATTERN,
    SEARCH_ALERTS_ORAL_ARGUMENT_ES_HL_FIELDS,
    SEARCH_HL_TAG,
    SEARCH_OPINION_CHILD_HL_FIELDS,
    SEARCH_OPINION_HL_FIELDS,
    SEARCH_OPINION_QUERY_FIELDS,
    SEARCH_ORAL_ARGUMENT_ES_HL_FIELDS,
    SEARCH_ORAL_ARGUMENT_QUERY_FIELDS,
    SEARCH_PEOPLE_CHILD_QUERY_FIELDS,
    SEARCH_PEOPLE_PARENT_QUERY_FIELDS,
    SEARCH_RECAP_CHILD_EXCLUDE_FIELDS,
    SEARCH_RECAP_CHILD_HL_FIELDS,
    SEARCH_RECAP_CHILD_QUERY_FIELDS,
    SEARCH_RECAP_HL_FIELDS,
    SEARCH_RECAP_PARENT_QUERY_FIELDS,
)
from cl.search.exception import (
    BadProximityQuery,
    QueryType,
    UnbalancedParenthesesQuery,
    UnbalancedQuotesQuery,
)
from cl.search.forms import SearchForm
from cl.search.models import (
    PRECEDENTIAL_STATUS,
    SEARCH_TYPES,
    Court,
    OpinionCluster,
    RECAPDocument,
)

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


def build_numeric_range_query(
    field: str,
    lower_bound: int | float,
    upper_bound: int | float,
    relation: Literal["INTERSECTS", "CONTAINS", "WITHIN", None] = None,
) -> list[Range]:
    """Returns documents that contain terms within a provided range.

    :param field: Elasticsearch fieldname
    :param lower_bound: _description_
    :param upper_bound: _description_
    :param relation: Indicates how the range query matches values for range fields. Defaults to None.
    :return: Empty list or list with DSL Range query
    """
    if not any([lower_bound, upper_bound]):
        return []

    params: ESRangeQueryParams = {"gte": lower_bound, "lte": upper_bound}
    if relation is not None:
        allowed_relations = ["INTERSECTS", "CONTAINS", "WITHIN"]
        assert (
            relation in allowed_relations
        ), f"'{relation}' is not an allowed relation."
        params["relation"] = relation

    return [Q("range", **{field: params})]


def build_daterange_query(
    field: str,
    before: date,
    after: date,
    relation: Literal["INTERSECTS", "CONTAINS", "WITHIN", None] = None,
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


def build_more_like_this_query(related_id: list[str]):
    document_list = [{"_id": f"o_{id}"} for id in related_id]
    more_like_this_fields = SEARCH_OPINION_QUERY_FIELDS
    more_like_this_fields.extend(
        [
            "type",
            "text",
            "caseName",
            "docketNumber",
        ]
    )
    return Q(
        "more_like_this",
        fields=more_like_this_fields,
        like=document_list,
        min_term_freq=1,
        max_query_terms=12,
    )


def make_es_boost_list(fields: Dict[str, float]) -> list[str]:
    """Constructs a list of Elasticsearch fields with their corresponding
    boost values.

    :param fields: A dictionary where keys are field names and values are
    the corresponding boost values.
    :return: A list of Elasticsearch fields with boost values formatted as 'field_name^boost_value'.
    """
    return [f"{k}^{v}" for k, v in fields.items()]


def add_fields_boosting(
    cd: CleanData, fields: list[str] | None = None
) -> list[str]:
    """Applies boosting to specific fields according the search type.

    :param cd: The user input CleanedData
    :param fields: If provided, a custom fields list to apply boosting,
    otherwise apply to all fields.
    :return: A list of Elasticsearch fields with their respective boost values.
    """
    # Apply standard qf parameters
    qf = BOOSTS["qf"][cd["type"]].copy()
    if cd["type"] in [
        SEARCH_TYPES.RECAP,
        SEARCH_TYPES.DOCKETS,
        SEARCH_TYPES.RECAP_DOCUMENT,
    ]:
        qf = BOOSTS["es"][cd["type"]].copy()

    if cd["type"] in [
        SEARCH_TYPES.ORAL_ARGUMENT,
        SEARCH_TYPES.RECAP,
        SEARCH_TYPES.DOCKETS,
        SEARCH_TYPES.RECAP_DOCUMENT,
        SEARCH_TYPES.OPINION,
    ]:
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

    if fields:
        qf = {key: value for key, value in qf.items() if key in fields}
    return make_es_boost_list(qf)


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


def validate_query_syntax(value: str, query_type: QueryType) -> None:
    """Validate the syntax of a query string. It checks for common syntax
    errors in query strings, such as unbalanced parentheses, unbalanced quotes,
    and unrecognized proximity tokens. If any of these errors are found, the
    corresponding exception is raised.

    :param value: The query string to validate.
    :param query_type: The type of the query, used to specify the context in
    which the validation is being performed.
    :return: None, it raises the corresponding exception.
    """

    if check_unbalanced_parenthesis(value):
        raise UnbalancedParenthesesQuery(
            "The query contains unbalanced parentheses.", query_type
        )
    if check_unbalanced_quotes(value):
        raise UnbalancedQuotesQuery(
            "The query contains unbalanced quotes.", query_type
        )
    if check_for_proximity_tokens(value):
        raise BadProximityQuery(
            "The query contains an unrecognized proximity token.", query_type
        )


def build_fulltext_query(
    fields: list[str], value: str, only_queries=False
) -> QueryString | List:
    """Given the cleaned data from a form, return a Elastic Search string query or []
    https://www.elastic.co/guide/en/elasticsearch/reference/current/full-text-queries.html

    :param fields: A list of name fields to search in.
    :param value: The string value to search for.
    :param only_queries: If True return only the queries avoiding wrapping them
    into a bool clause.
    :return: A Elasticsearch QueryString or [] if the "value" param is empty.
    """
    if value:
        validate_query_syntax(value, QueryType.QUERY_STRING)
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
                fuzziness=2,
            ),
            Q(
                "query_string",
                fields=fields,
                query=query_value,
                quote_field_suffix=".exact",
                default_operator="AND",
                type="phrase",
                fuzziness=2,
            ),
        ]
        if only_queries:
            return q_should
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

    if isinstance(value, str):
        validate_query_syntax(value, QueryType.FILTER)

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
        if isinstance(value, str):
            validate_query_syntax(value, QueryType.FILTER)
        return [
            Q(
                "query_string",
                query=value,
                fields=[field],
                default_operator="AND",
            )
        ]
    return []


def toggle_sort_order(
    order_by: str | None, toggle_sorting: bool
) -> str | None:
    """Toggle the sorting order of the given "order_by" string from ascending
    to descending, or vice versa. This is used for changing the sort direction
    in queries, useful to perform backward pagination for the V4 Search API.

    :param order_by: A string specifying the fields and sort directions,
    separated by commas, e.g., "score asc, score desc".
    :param toggle_sorting: A boolean flag that indicates whether the sorting
    order should be toggled. If False, the original "order_by" is returned.
    :return: A modified "order_by" string with toggled sort directions.
    """

    if toggle_sorting and order_by:
        sort_components = order_by.split(",")
        toggle_sort_components = []
        for component in sort_components:
            component = component.strip()
            if "desc" in component:
                toggle_sort_components.append(component.replace("desc", "asc"))
            elif "asc" in component:
                toggle_sort_components.append(component.replace("asc", "desc"))
            else:
                toggle_sort_components.append(component)

        return ", ".join(toggle_sort_components)

    return order_by


def build_sort_results(
    cd: CleanData,
    toggle_sorting: bool = False,
    api_version: Literal["v3", "v4"] | None = None,
) -> Dict:
    """Given cleaned data, find order_by value and return dict to use with
    ElasticSearch sort

    :param cd: The user input CleanedData
    :param toggle_sorting: Whether to toggle the sorting order to perform backward
    pagination for the V4 Search API.
    :param api_version: Optional, the request API version.
    :return: The short dict.
    """

    order_by = cd.get("order_by")
    order_by = toggle_sort_order(order_by, toggle_sorting)
    order_by_map = {
        "score desc": {"_score": {"order": "desc"}},
        "score asc": {"_score": {"order": "asc"}},
        "dateArgued desc": {"dateArgued": {"order": "desc"}},
        "dateArgued asc": {"dateArgued": {"order": "asc"}},
        "random_ desc": {"random_": {"order": "desc"}},
        "random_ asc": {"random_": {"order": "asc"}},
        "name_reverse asc": {"name_reverse": {"order": "asc"}},
        "docket_id asc": {"docket_id": {"order": "asc"}},
        "docket_id desc": {"docket_id": {"order": "desc"}},
        "cluster_id asc": {"cluster_id": {"order": "asc"}},
        "cluster_id desc": {"cluster_id": {"order": "desc"}},
        "id asc": {"id": {"order": "asc"}},
        "id desc": {"id": {"order": "desc"}},
        "dob desc,name_reverse asc": {
            "dob": {"order": "desc"},
            "name_reverse": {"order": "asc"},
        },
        "dob asc,name_reverse asc": {
            "dob": {"order": "asc"},
            "name_reverse": {"order": "asc"},
        },
        "dod desc,name_reverse asc": {
            "dod": {"order": "desc"},
            "name_reverse": {"order": "asc"},
        },
        "dateFiled desc": {"dateFiled": {"order": "desc"}},
        "dateFiled asc": {"dateFiled": {"order": "asc"}},
        # For child sorting keys use always "order": "desc", the sorting will
        # be handled internally by a function score in the has_child query.
        "entry_date_filed asc": {"_score": {"order": "desc"}},
        "entry_date_filed desc": {"_score": {"order": "desc"}},
        "entry_date_filed_feed desc": {"entry_date_filed": {"order": "desc"}},
        "citeCount desc": {"citeCount": {"order": "desc"}},
        "citeCount asc": {"citeCount": {"order": "asc"}},
    }

    if api_version == "v4":
        # Override dateFiled sorting keys in V4 API to work alongside the custom
        # function score for sorting by dateFiled.
        order_by_map["dateFiled desc"] = {"_score": {"order": "desc"}}
        order_by_map["dateFiled asc"] = {"_score": {"order": "desc"}}

    if toggle_sorting and api_version == "v4":
        # Override the sorting keys in the V4 API when toggle_sorting is True
        # for backward cursor pagination based on fields that use a custom
        # function score.
        order_by_map["entry_date_filed asc"] = {"_score": {"order": "asc"}}
        order_by_map["entry_date_filed desc"] = {"_score": {"order": "asc"}}
        order_by_map["dateFiled desc"] = {"_score": {"order": "asc"}}
        order_by_map["dateFiled asc"] = {"_score": {"order": "asc"}}

    if cd["type"] == SEARCH_TYPES.PARENTHETICAL:
        order_by_map["score desc"] = {"score": {"order": "desc"}}

    if cd["type"] in [
        SEARCH_TYPES.RECAP,
        SEARCH_TYPES.DOCKETS,
        SEARCH_TYPES.RECAP_DOCUMENT,
    ]:
        random_order_field_id = "docket_id"
    elif cd["type"] in [SEARCH_TYPES.OPINION]:
        random_order_field_id = "cluster_id"
    else:
        random_order_field_id = "id"

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
                    "source": f"Long.hashCode(doc['{random_order_field_id}'].value ^ params.seed)",
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


def get_child_sorting_key(
    cd: CleanData, api_version: Literal["v3", "v4"] | None = None
) -> tuple[str, str]:
    """Given cleaned data, find order_by value and return a key to use within
    a has_child query.

    :param cd: The user input CleanedData
    :param api_version: Optional, the request API version.
    :return: A two tuple containing the short key and the order (asc or desc).
    """
    order_by_map_child = {
        "entry_date_filed asc": ("entry_date_filed", "asc"),
        "entry_date_filed desc": ("entry_date_filed", "desc"),
    }
    if api_version == "v4":
        order_by_map_child.update(
            {
                "dateFiled desc": ("dateFiled", "desc"),
                "dateFiled asc": ("dateFiled", "asc"),
            }
        )
    order_by = cd.get("order_by", "")
    return order_by_map_child.get(order_by, ("", ""))


def extend_selected_courts_with_child_courts(
    selected_courts: list[str],
) -> list[str]:
    """Extend the list of selected courts with their corresponding child courts

    :param selected_courts: A list of court IDs.
    :return: A list of unique court IDs, including both the original and their
    corresponding child courts.
    """

    unique_courts = set(selected_courts)
    unique_courts.update(lookup_child_courts(list(unique_courts)))
    return list(unique_courts)


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
                extend_selected_courts_with_child_courts(
                    cd.get("court", "").split()
                ),
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


def build_highlights_dict(
    highlighting_fields: dict[str, int] | None,
    hl_tag: str,
    child_highlighting: bool = True,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Builds a dictionary for ES highlighting options and a list of fields to
    exclude from the _source.

    :param highlighting_fields: A dictionary of fields to highlight in child docs.
    :param hl_tag: The HTML tag to use for highlighting matched fragments.
    :param child_highlighting: Whether highlighting should be enabled in child docs.
    :return: A tuple containing, a dictionary with the configuration for
    highlighting each field and aa list of field names to exclude from the
    _source results to avoid data redundancy.
    """

    if highlighting_fields is None:
        highlighting_fields = {}
    highlight_options: dict[str, dict[str, Any]] = {"fields": {}}

    fields_to_exclude = []
    for field, fragment_size in highlighting_fields.items():
        number_of_fragments = 1 if fragment_size else 0
        # In fields that have a defined fragment size in their HL mapping
        # e.g., SEARCH_RECAP_CHILD_HL_FIELDS, a 'no_match_size' parameter
        # is also set. If there are no matching fragments to highlight,
        # this setting will return a specified amount of text from the
        # beginning of the field.
        no_match_size = settings.NO_MATCH_HL_SIZE if fragment_size else 0
        if fragment_size and not field.endswith("exact"):
            # The original field is excluded from the response to avoid
            # returning the entire field from the index.
            fields_to_exclude.append(field)
            if not child_highlighting:
                # If highlighting is not enabled in child documents, return
                # only the fields to exclude.
                continue

        highlight_options["fields"][field] = {
            "type": settings.ES_HIGHLIGHTER,
            "matched_fields": [field, f"{field}.exact"],
            "fragment_size": fragment_size,
            "no_match_size": no_match_size,
            "number_of_fragments": number_of_fragments,
            "pre_tags": [f"<{hl_tag}>"],
            "post_tags": [f"</{hl_tag}>"],
        }

    return highlight_options, fields_to_exclude


def build_custom_function_score_for_date(
    query: QueryString | str, order_by: tuple[str, str], default_score: int
) -> QueryString:
    """Build a custom function score query for based on a date field.

    Define the function score for sorting, based on the child sort_field. When
    the order is 'entry_date_filed desc', the 'date_filed_time' value, adjusted
    by washington_bd_offset, is used as the score, sorting newer documents
    first. In 'asc' order, the score is the difference between 'current_time'
    (also adjusted by the washington_bd_offset) and 'date_filed_time',
    prioritizing older documents. If a document does not have a 'date_filed'
    set, the function returns 1. This ensures that dockets containing documents
    without a 'date_filed' are displayed before dockets without filings, which
    have a default score of 0. washington_bd_offset is based on George
    Washington's birthday (February 22, 1732), ensuring all epoch millisecond
    values are positive and compatible with ES scoring system. This approach
    allows for handling dates in our system both before and after January 1, 1970 (epoch time),
    within a positive scoring range.

    :param query: The Elasticsearch query string or QueryString object.
    :param order_by: If provided the field to use to compute score for sorting
    results based on a child document field.
    :param default_score: The default score to return when the document lacks
    the sort field.
    :return: The modified QueryString object with applied function score.
    """

    sort_field, order = order_by
    query = Q(
        "function_score",
        query=query,
        script_score={
            "script": {
                "source": f"""
                    // Check if the document has a value for the 'sort_field'
                    if (doc['{sort_field}'].size() == 0) {{
                        return {default_score};  // If not, return 'default_score' as the score
                    }} else {{
                        // Offset based on the positive epoch time for Washington's birthday to ensure positive scores.
                        // (February 22, 1732)
                        long washington_bd_offset = 7506086400000L;
                        // Get the current time in milliseconds, include the washington_bd_offset to work with positive epoch times.
                        long current_time = new Date().getTime() + washington_bd_offset;

                        // Convert the 'sort_field' value to epoch milliseconds, adjusting by the same offset.
                        long date_filed_time = doc['{sort_field}'].value.toInstant().toEpochMilli() + washington_bd_offset;

                        // If the order is 'desc', return the 'date_filed_time' as the score
                        if (params.order.equals('desc')) {{
                            return date_filed_time;
                        }} else {{
                            // Otherwise, calculate the difference between current time and 'date_filed_time'
                            // in order to boost older documents if the order is asc.
                            long diff = current_time - date_filed_time;

                            // Return the difference if it's non-negative, otherwise return 'default_score'
                            return diff >= 0 ? diff : {default_score};
                        }}
                    }}
                        """,
                # Parameters passed to the script
                "params": {"order": order, "default_score": default_score},
            },
        },
        # Replace the original score with the one computed by the script
        boost_mode="replace",
    )

    return query


def build_has_child_query(
    query: QueryString | str,
    child_type: str,
    child_hits_limit: int,
    highlighting_fields: dict[str, int] | None = None,
    order_by: tuple[str, str] | None = None,
    child_highlighting: bool = True,
    api_version: Literal["v3", "v4"] | None = None,
) -> QueryString:
    """Build a 'has_child' query.

    :param query: The Elasticsearch query string or QueryString object.
    :param child_type: The type of the child document.
    :param child_hits_limit: The maximum number of child hits to be returned.
    :param highlighting_fields: List of fields to highlight in child docs.
    :param order_by: If provided the field to use to compute score for sorting
    results based on a child document field.
    :param child_highlighting: Whether highlighting should be enabled in child docs.
    :param api_version: Optional, the request API version.
    :return: The 'has_child' query.
    """

    if order_by and all(order_by) and child_type == "recap_document":
        if api_version == "v4":
            query = nullify_query_score(query)
        else:
            query = build_custom_function_score_for_date(
                query, order_by, default_score=1
            )

    highlight_options, fields_to_exclude = build_highlights_dict(
        highlighting_fields, SEARCH_HL_TAG, child_highlighting
    )

    inner_hits = {
        "name": f"filter_query_inner_{child_type}",
        "size": child_hits_limit,
        "_source": {
            "excludes": fields_to_exclude,
        },
    }
    if highlight_options and child_highlighting:
        inner_hits["highlight"] = highlight_options

    return Q(
        "has_child",
        type=child_type,
        score_mode="max",
        query=query,
        inner_hits=inner_hits,
    )


def get_search_query(
    cd: CleanData,
    search_query: Search,
    filters: list,
    string_query: QueryString,
    api_version: Literal["v3", "v4"] | None = None,
) -> Search:
    """Get the appropriate search query based on the given parameters.

    :param cd: The query CleanedData
    :param search_query: Elasticsearch DSL Search object
    :param filters: A list of filter objects to be applied.
    :param string_query: An Elasticsearch QueryString object.
    :param api_version: Optional, the request API version.
    :return: The modified Search object based on the given conditions.
    """
    if not any([filters, string_query]):
        match cd["type"]:
            case SEARCH_TYPES.PEOPLE:
                return search_query.query(Q("match", person_child="person"))
            case SEARCH_TYPES.RECAP | SEARCH_TYPES.DOCKETS:
                # Match all query for RECAP and Dockets, it'll return dockets
                # with child documents and also empty dockets.
                _, query_hits_limit = get_child_top_hits_limit(cd, cd["type"])
                match_all_child_query = build_has_child_query(
                    "match_all",
                    "recap_document",
                    query_hits_limit,
                    SEARCH_RECAP_CHILD_HL_FIELDS,
                    get_child_sorting_key(cd, api_version),
                    api_version=api_version,
                )
                match_all_parent_query = apply_custom_score_to_parent_query(
                    cd, Q("match", docket_child="docket"), api_version
                )
                return search_query.query(
                    Q(
                        "bool",
                        should=[match_all_child_query, match_all_parent_query],
                    )
                )
            case SEARCH_TYPES.OPINION:
                # Only return Opinion clusters.
                q_should = [
                    Q(
                        "has_child",
                        type="opinion",
                        score_mode="max",
                        query=Q("match_all"),
                        inner_hits={
                            "name": "text_query_inner_opinion",
                            "size": 10,
                        },
                    ),
                    Q("match", cluster_child="opinion_cluster"),
                ]
                search_query = search_query.query(
                    Q("bool", should=q_should, minimum_should_match=1)
                )
            case _:
                return search_query.query("match_all")

    if string_query:
        search_query = search_query.query(string_query)

    if filters:
        search_query = search_query.filter(reduce(operator.iand, filters))

    return search_query


def build_es_base_query(
    search_query: Search,
    cd: CleanData,
    child_highlighting: bool = True,
    api_version: Literal["v3", "v4"] | None = None,
) -> tuple[Search, QueryString | None]:
    """Builds filters and fulltext_query based on the given cleaned
     data and returns an elasticsearch query.

    :param search_query: The Elasticsearch search query object.
    :param cd: The cleaned data object containing the query and filters.
    :param child_highlighting: Whether highlighting should be enabled in child docs.
    :param api_version: Optional, the request API version.
    :return: A two-tuple, the Elasticsearch search query object and an ES
    QueryString for child documents, or None if there is no need to query
    child documents.
    """

    string_query = None
    join_query = None
    join_field_documents = [SEARCH_TYPES.PEOPLE]
    if cd["type"] in join_field_documents:
        filters = build_join_es_filters(cd)
    else:
        filters = build_es_filters(cd)

    match cd["type"]:
        case SEARCH_TYPES.PARENTHETICAL:
            string_query = build_fulltext_query(
                ["representative_text"], cd.get("q", "")
            )
        case SEARCH_TYPES.ORAL_ARGUMENT:
            fields = SEARCH_ORAL_ARGUMENT_QUERY_FIELDS.copy()
            fields.extend(add_fields_boosting(cd))
            string_query = build_fulltext_query(
                fields,
                cd.get("q", ""),
            )
        case SEARCH_TYPES.PEOPLE:
            child_fields = SEARCH_PEOPLE_CHILD_QUERY_FIELDS.copy()
            child_fields.extend(
                add_fields_boosting(
                    cd,
                    [
                        "appointer",
                        "supervisor",
                        "predecessor",
                    ],
                )
            )
            child_query_fields = {
                "position": child_fields,
            }
            parent_query_fields = SEARCH_PEOPLE_PARENT_QUERY_FIELDS.copy()
            parent_query_fields.extend(
                add_fields_boosting(
                    cd,
                    [
                        "name",
                    ],
                )
            )
            string_query = build_join_fulltext_queries(
                child_query_fields,
                parent_query_fields,
                cd.get("q", ""),
            )
        case (
            SEARCH_TYPES.RECAP
            | SEARCH_TYPES.DOCKETS
            | SEARCH_TYPES.RECAP_DOCUMENT
        ):
            child_fields = SEARCH_RECAP_CHILD_QUERY_FIELDS.copy()
            child_fields.extend(
                add_fields_boosting(
                    cd,
                    [
                        "description",
                        # Docket Fields
                        "docketNumber",
                        "caseName",
                    ],
                )
            )
            child_query_fields = {"recap_document": child_fields}
            parent_query_fields = SEARCH_RECAP_PARENT_QUERY_FIELDS.copy()
            parent_query_fields.extend(
                add_fields_boosting(
                    cd,
                    [
                        "docketNumber",
                        "caseName",
                    ],
                )
            )
            string_query, join_query = build_full_join_es_queries(
                cd,
                child_query_fields,
                parent_query_fields,
                child_highlighting=child_highlighting,
                api_version=api_version,
            )
        case SEARCH_TYPES.OPINION:
            str_query = cd.get("q", "")
            related_match = RELATED_PATTERN.search(str_query)
            mlt_query = None
            if related_match:
                cluster_pks = related_match.group("pks").split(",")
                mlt_query = build_more_like_this_query(cluster_pks)
            opinion_search_fields = SEARCH_OPINION_QUERY_FIELDS
            child_fields = opinion_search_fields.copy()
            child_fields.extend(
                add_fields_boosting(
                    cd,
                    [
                        "type",
                        "text",
                        "caseName",
                        "docketNumber",
                    ],
                ),
            )
            child_query_fields = {"opinion": child_fields}
            parent_query_fields = opinion_search_fields.copy()
            parent_query_fields.extend(
                add_fields_boosting(
                    cd,
                    [
                        "caseName",
                        "docketNumber",
                    ],
                )
            )
            string_query, join_query = build_full_join_es_queries(
                cd,
                child_query_fields,
                parent_query_fields,
                mlt_query,
            )

    search_query = get_search_query(
        cd, search_query, filters, string_query, api_version
    )
    return search_query, join_query


def build_has_parent_parties_query(
    parties_filters: list[QueryString],
) -> QueryString | None:
    """Build a has_parent query based on the parties fields (party and attorney).

    This method is used where it is required to include all the RECAPDocuments
    that belong to dockets matching a query that includes party filters.
    It is applicable in scenarios such as the child document count query and
    the RECAP Search feed.

    :param parties_filters: A list of party and or attorney filters.
    :return: An ES has parent query or None if there are no parties_filters.
    """

    if parties_filters:
        return Q(
            "has_parent",
            parent_type="docket",
            query=Q(
                "bool",
                filter=parties_filters,
            ),
        )
    return None


def build_child_docs_query(
    join_query: QueryString | None,
    cd: CleanData,
    exclude_docs_for_empty_field: str = "",
) -> QueryString:
    """Build a query for counting child documents in Elasticsearch, using the
    has_child query filters and queries. And append a match filter to only
    retrieve RECAPDocuments.

    :param join_query: Existing Elasticsearch QueryString object or None
    :param cd: The user input CleanedData
    :param exclude_docs_for_empty_field: Field that should not be empty for a
    document to be included
    :return: An Elasticsearch QueryString object
    """

    child_query_opinion = Q("match", cluster_child="opinion")
    child_query_recap = Q("match", docket_child="recap_document")
    parent_filters = build_join_es_filters(cd)
    parties_filters = [
        query
        for query in parent_filters
        if isinstance(query, QueryString)
        and query.fields[0] in ["party", "attorney"]
    ]
    parties_has_parent_query = build_has_parent_parties_query(parties_filters)

    if not join_query:
        # Match all query case.
        if not exclude_docs_for_empty_field:
            if cd["type"] == SEARCH_TYPES.OPINION:
                return child_query_opinion
            else:
                if parties_has_parent_query:
                    return parties_has_parent_query
                return child_query_recap
        else:
            filters = [
                Q("exists", field=exclude_docs_for_empty_field),
            ]

            if cd["type"] == SEARCH_TYPES.OPINION:
                filters.append(child_query_opinion)
            else:
                if parties_has_parent_query:
                    filters.append(parties_has_parent_query)
                filters.append(child_query_recap)
            return Q("bool", filter=filters)

    query_dict = join_query.to_dict()
    if "filter" in query_dict["bool"]:
        existing_filter = query_dict["bool"]["filter"]
        if cd["type"] == SEARCH_TYPES.OPINION:
            existing_filter.append(child_query_opinion)
        else:
            # RECAP case: Append has_parent query with parties filters.
            if parties_has_parent_query:
                existing_filter.append(parties_has_parent_query)
            existing_filter.append(child_query_recap)
        if exclude_docs_for_empty_field:
            existing_filter.append(
                Q("exists", field=exclude_docs_for_empty_field)
            )
    else:
        if cd["type"] == SEARCH_TYPES.OPINION:
            query_dict["bool"]["filter"] = [child_query_opinion]
        else:
            query_dict["bool"]["filter"] = [child_query_recap]
            # RECAP case: Append has_parent query with parties filters.
            if parties_has_parent_query:
                query_dict["bool"]["filter"].append(parties_has_parent_query)
        if exclude_docs_for_empty_field:
            query_dict["bool"]["filter"].append(
                Q("exists", field=exclude_docs_for_empty_field)
            )

    return Q(query_dict)


def get_only_status_facets(
    search_query: Search, search_form: SearchForm
) -> list[BoundField]:
    """Create a useful facet variable to use in a template

    This method creates an Elasticsearch query with the status aggregations
    and sets the size to 0 to ensure that no documents are returned.
    :param search_query: The Elasticsearch search query object.
    :param search_form: The form displayed in the user interface
    """
    search_query = search_query.extra(size=0)
    # filter out opinions and get just the clusters
    search_query = search_query.query(
        Q("bool", must=Q("match", cluster_child="opinion_cluster"))
    )
    search_query.aggs.bucket("status", A("terms", field="status.raw"))
    response = search_query.execute()
    return make_es_stats_variable(search_form, response)


def get_facet_dict_for_search_query(
    search_query: Search, cd: CleanData, search_form: SearchForm
):
    """Create facets variables to use in a template omitting the stat_ filter
    so the facets counts consider cluster for all status.

    :param search_query: The Elasticsearch search query object.
    :param cd: The user input CleanedData
    :param search_form: The form displayed in the user interface
    """

    cd["just_facets_query"] = True
    search_query, _ = build_es_base_query(search_query, cd)
    search_query.aggs.bucket("status", A("terms", field="status.raw"))
    search_query = search_query.extra(size=0)
    response = search_query.execute()
    return make_es_stats_variable(search_form, response)


def build_es_main_query(
    search_query: Search, cd: CleanData
) -> tuple[Search, Search | None, int | None]:
    """Builds and returns an elasticsearch query based on the given cleaned
     data, also performs grouping if required, add highlighting and returns
     additional query related metrics.

    :param search_query: The Elasticsearch search query object.
    :param cd: The cleaned data object containing the query and filters.
    :return: A three tuple, the Elasticsearch search query object after applying
    filters, string query and grouping if needed, the child documents count
    query if required, the total number of top hits returned by a group if
    applicable.
    """
    search_query_base = search_query
    search_query, join_query = build_es_base_query(search_query, cd)
    top_hits_limit = 5
    child_docs_count_query = None
    match cd["type"]:
        case SEARCH_TYPES.PARENTHETICAL:
            # Create groups aggregation, add highlight and
            # sort the results of a parenthetical query.
            search_query, top_hits_limit = group_search_results(
                search_query,
                cd,
                build_sort_results(cd),
            )
            return (
                search_query,
                child_docs_count_query,
                top_hits_limit,
            )
        case SEARCH_TYPES.RECAP | SEARCH_TYPES.DOCKETS:
            child_docs_count_query = build_child_docs_query(join_query, cd)
            if child_docs_count_query:
                # Get the total RECAP Documents count.
                child_docs_count_query = search_query_base.query(
                    child_docs_count_query
                )
        case _:
            pass

    search_query = add_es_highlighting(search_query, cd)
    search_query = search_query.sort(build_sort_results(cd))

    return (
        search_query,
        child_docs_count_query,
        top_hits_limit,
    )


def add_es_highlighting(
    search_query: Search, cd: CleanData, alerts: bool = False
) -> Search:
    """Add elasticsearch highlighting to the search query.

    :param search_query: The Elasticsearch search query object.
    :param cd: The user input CleanedData
    :param alerts: If highlighting is being applied to search Alerts hits.
    :return: The modified Elasticsearch search query object with highlights set
    """
    fields_to_exclude = []
    highlighting_fields = []
    highlighting_keyword_fields = []
    hl_tag = ALERTS_HL_TAG if alerts else SEARCH_HL_TAG
    match cd["type"]:
        case SEARCH_TYPES.ORAL_ARGUMENT:
            highlighting_fields = (
                SEARCH_ALERTS_ORAL_ARGUMENT_ES_HL_FIELDS
                if alerts
                else SEARCH_ORAL_ARGUMENT_ES_HL_FIELDS
            )
            fields_to_exclude = ["sha1"]
        case SEARCH_TYPES.PEOPLE:
            highlighting_fields = PEOPLE_ES_HL_FIELDS
            highlighting_keyword_fields = PEOPLE_ES_HL_KEYWORD_FIELDS
        case SEARCH_TYPES.RECAP | SEARCH_TYPES.DOCKETS:
            highlighting_fields = SEARCH_RECAP_HL_FIELDS
        case SEARCH_TYPES.OPINION:
            highlighting_fields = SEARCH_OPINION_HL_FIELDS

    search_query = search_query.source(excludes=fields_to_exclude)
    # Use FVH in testing and documents that already support FVH.
    for field in highlighting_fields:
        search_query = search_query.highlight(
            field,
            type=settings.ES_HIGHLIGHTER,
            matched_fields=[field, f"{field}.exact"],
            number_of_fragments=0,
            pre_tags=[f"<{hl_tag}>"],
            post_tags=[f"</{hl_tag}>"],
        )
    # Keyword fields do not support term_vector indexing; thus, FVH is not
    # supported either. Use plain text in this case. Keyword fields don't
    # have an exact version, so no HL merging is required either.
    if highlighting_keyword_fields:
        for field in highlighting_keyword_fields:
            search_query = search_query.highlight(
                field,
                type="plain",
                number_of_fragments=0,
                pre_tags=[f"<{hl_tag}>"],
                post_tags=[f"</{hl_tag}>"],
            )

    return search_query


def merge_highlights_into_result(
    highlights: dict[str, Any],
    result: AttrDict | dict[str, Any],
) -> None:
    """Merges the highlighted terms into the search result.
    This function integrates highlighted terms from the meta highlights result
    into the corresponding search results.

    :param highlights: The AttrDict object containing highlighted fields and
    their highlighted terms.
    :param result: The result AttrDict object
    :return: None, the function updates the results in place.
    """

    for (
        field,
        highlight_list,
    ) in highlights.items():
        result[field] = highlight_list


def set_results_highlights(results: Page | Response, search_type: str) -> None:
    """Sets the highlights for each search result in a Page object by updating
    related fields in _source dict.

    :param results: The Page or Response object containing search results.
    :param search_type: The search type to perform.
    :return: None, the function updates the results in place.
    """

    results_list = results
    if isinstance(results, Page):
        results_list = results.object_list

    for result in results_list:
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
            if hasattr(result.meta, "highlight"):
                highlights = result.meta.highlight.to_dict()
                merge_highlights_into_result(
                    highlights,
                    result,
                )

            # Merge child document highlights
            if not hasattr(result, "child_docs"):
                continue

            for child_doc in result.child_docs:
                if hasattr(child_doc, "highlight"):
                    highlights = child_doc.highlight.to_dict()
                    merge_highlights_into_result(
                        highlights,
                        child_doc["_source"],
                    )


def group_search_results(
    search: Search,
    cd: CleanData,
    order_by: dict[str, dict[str, str]],
) -> tuple[Search, int]:
    """Group search results by a specified field and return top hits for each
    group.

    :param search: The elasticsearch Search object representing the query.
    :param cd: The cleaned data object containing the query and filters.
    :param order_by: The field name to use for sorting the top hits.
    :return: The modified Elasticsearch search query with highlights and aggregations
    """

    # If cluster_id query set the top_hits_limit to 100
    # Top hits limit in elasticsearch is 100
    cluster_query = re.search(r"cluster_id:\d+", cd["q"])
    size = 5 if not cluster_query else 100
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

    return search, size


def convert_str_date_fields_to_date_objects(
    results: Page, search_type: str
) -> None:
    """Converts string date fields in Elasticsearch search results to date
    objects.

    :param results: A Page object containing the search results to be modified.
    :param search_type: The search type to perform.
    :return: None, the function modifies the search results object in place.
    """
    if search_type == SEARCH_TYPES.PARENTHETICAL:
        date_field_name = "dateFiled"
        for result in results.object_list:
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


def fill_position_mapping(
    positions: QuerySet[Position],
    request_type: Literal["frontend", "api"] = "frontend",
) -> BasePositionMapping | ApiPositionMapping:
    """Extract all the data from the position queryset and
    fill the attributes of the mapping.

    :param positions: List of position records.
    :param request_type: The request type, fronted or api.
    :return: PositionMapping, the function fill the attributes of the mapping.
    """
    position_db_mapping = (
        BasePositionMapping()
        if request_type == "frontend"
        else ApiPositionMapping()
    )
    db_to_dataclass_map = position_db_mapping.get_db_to_dataclass_map()

    for position in positions:
        # Add data to the mapping using the judge ID as a key.
        # API and Frontend
        person_id = position.person.pk
        for validation, value in db_to_dataclass_map.items():
            if not getattr(position, validation, None):
                continue

            for db_field, position_field in value.items():
                mapping_dict = getattr(position_db_mapping, position_field)
                for key, attr in enumerate(db_field.split("__")):
                    field_value = (
                        getattr(position, attr)
                        if not key
                        else getattr(field_value, attr)  # type: ignore
                    )

                if callable(field_value):
                    field_value = field_value()
                elif isinstance(field_value, (datetime, date)):
                    field_value = midnight_pt(field_value)

                mapping_dict[person_id].append(field_value)

    return position_db_mapping


def merge_unavailable_fields_on_parent_document(
    results: Page | dict | Response,
    search_type: str,
    request_type: Literal["frontend", "api"] = "frontend",
    highlight: bool = True,
) -> None:
    """Merges unavailable fields on parent document from the database into
    search results, not all fields are required in frontend, so that fields are
    completed according to the received request_type (frontend or api).

    :param results: A Page object containing the search results to be modified.
    :param search_type: The search type to perform.
    :param request_type: The request type, frontend or api.
    :param highlight: Whether highlighting is enabled.
    :return: None, the function modifies the search results object in place.
    """

    match search_type:
        case SEARCH_TYPES.PEOPLE:
            # Merge positions courts.
            person_ids = [d["id"] for d in results]
            positions_in_page = Position.objects.filter(
                person_id__in=person_ids
            ).select_related(
                "person",
                "court",
                "appointer",
                "appointer__person",
                "supervisor",
                "predecessor",
            )
            position_db_mapping = fill_position_mapping(
                positions_in_page, request_type
            )

            for result in results:
                person_id = result["id"]
                for field in fields(position_db_mapping):
                    position_dict = getattr(position_db_mapping, field.name)
                    value = position_dict.get(person_id)
                    cleaned_name = re.sub("_dict", "", field.name)
                    result[cleaned_name] = value
        case (
            SEARCH_TYPES.RECAP | SEARCH_TYPES.RECAP_DOCUMENT
        ) if request_type == "api" and not highlight:
            # Retrieves the plain_text from the DB to fill the snippet when
            # highlighting is disabled.

            if search_type == SEARCH_TYPES.RECAP:
                rd_ids = {
                    doc["_source"]["id"]
                    for entry in results
                    for doc in entry["child_docs"]
                }
            else:
                rd_ids = {entry["id"] for entry in results}

            recap_docs = (
                RECAPDocument.objects.filter(pk__in=rd_ids)
                .annotate(
                    plain_text_short=Substr(
                        "plain_text", 1, settings.NO_MATCH_HL_SIZE
                    )
                )
                .values("id", "plain_text_short")
            )
            recap_docs_dict = {
                doc["id"]: doc["plain_text_short"] for doc in recap_docs
            }
            for result in results:
                if search_type == SEARCH_TYPES.RECAP:
                    for rd in result["child_docs"]:
                        rd["_source"]["plain_text"] = recap_docs_dict[
                            rd["_source"]["id"]
                        ]
                else:
                    result["plain_text"] = recap_docs_dict[result["id"]]

        case _:
            return


def clean_count_query(search_query: Search) -> SearchDSL:
    """Cleans a given ES Search object for a count query.

    Modifies the input Search object by removing 'inner_hits' from
    any 'has_child' queries within the 'should' clause of the boolean query.
    It then creates a new Search object with the modified query.

    :param search_query: The ES Search object.
    :return: A new ES Search object with the count query.
    """

    parent_total_query_dict = search_query.to_dict()
    try:
        # Clean the has_child query in queries that contain it.
        for query in parent_total_query_dict["query"]["bool"]["should"]:
            if "has_child" in query and "inner_hits" in query["has_child"]:
                del query["has_child"]["inner_hits"]
    except KeyError:
        # Omit queries that don't contain it.
        pass

    # Select only the query and omit other elements like sorting, highlighting, etc
    parent_total_query_dict = parent_total_query_dict["query"]
    # Generate a new Search object from scratch
    search_query = SearchDSL(index=search_query._index)
    search_query = search_query.query(Q(parent_total_query_dict))
    return search_query


def fetch_es_results(
    get_params: QueryDict,
    search_query: Search,
    child_docs_count_query: Search | None,
    page: int = 1,
    rows_per_page: int = settings.SEARCH_PAGE_SIZE,
) -> tuple[Response | list, int, bool, int | None, int | None]:
    """Fetch elasticsearch results with pagination.

    :param get_params: The user get params.
    :param search_query: Elasticsearch DSL Search object
    :param child_docs_count_query: The ES Search object to perform the count
    for child documents if required, otherwise None.
    :param page: Current page number.
    :param rows_per_page: Number of records wanted per page.
    :return: A five-tuple: The ES main response, the ES query time, whether
    there was an error, the total number of hits for the main document, and
    the total number of hits for the child document.
    """

    child_total = None
    child_total_query = None
    # Default to page 1 if the user request page 0.
    page = page or 1
    # Compute "from" parameter for Elasticsearch
    es_from = (page - 1) * rows_per_page
    error = True
    try:
        main_query = search_query.extra(from_=es_from, size=rows_per_page)
        main_doc_count_query = clean_count_query(search_query)
        # Set size to 0 to avoid retrieving documents in the count queries for
        # better performance. Set track_total_hits to True to consider all the
        # documents.
        main_doc_count_query = main_doc_count_query.extra(
            size=0, track_total_hits=True
        )
        if child_docs_count_query:
            child_total_query = child_docs_count_query.extra(
                size=0, track_total_hits=True
            )

        # Execute the ES main query + count queries in a single request.
        multi_search = MultiSearch()
        multi_search = multi_search.add(main_query).add(main_doc_count_query)
        if child_total_query:
            multi_search = multi_search.add(child_total_query)
        responses = multi_search.execute()

        main_response = responses[0]
        main_doc_count_response = responses[1]
        parent_total = main_doc_count_response.hits.total.value
        if child_total_query:
            child_doc_count_response = responses[2]
            child_total = child_doc_count_response.hits.total.value

        query_time = main_response.took
        search_type = get_params.get("type", SEARCH_TYPES.OPINION)
        if (
            main_response.aggregations
            and search_type == SEARCH_TYPES.PARENTHETICAL
        ):
            main_response = main_response.aggregations.groups.buckets
        error = False
        return main_response, query_time, error, parent_total, child_total
    except (TransportError, ConnectionError, RequestError) as e:
        logger.warning(
            "Error loading search page with request: %s", dict(get_params)
        )
        logger.warning("Error was: %s", e)
        if settings.DEBUG is True:
            traceback.print_exc()
    except ApiError as e:
        if "Failed to parse query" in str(e):
            logger.warning("Failed to parse query: %s", e)
        else:
            logger.error("Multi-search API Error: %s", e)
    return [], 0, error, None, None


def build_join_fulltext_queries(
    child_query_fields: dict[str, list[str]],
    parent_fields: list[str],
    value: str,
    mlt_query: Query | None = None,
) -> QueryString | List:
    """Creates a full text query string for join parent-child documents.

    :param child_query_fields: A list of child name fields to search in.
    :param parent_fields: The parent fields to search in.
    :param value: The string value to search for.
    :param mlt_query: A More like this query, optional.
    :return: A Elasticsearch QueryString or [] if the "value" param is empty.
    """

    if not value and not mlt_query:
        return []
    q_should = []
    # Build  child documents fulltext queries.
    for child_type, fields in child_query_fields.items():
        highlight_options: dict[str, dict[str, Any]] = {"fields": {}}
        match child_type:
            case "opinion":
                highlight_options["fields"]["text"] = {
                    "type": "plain",
                    "fragment_size": 100,
                    "number_of_fragments": 100,
                    "pre_tags": ["<mark>"],
                    "post_tags": ["</mark>"],
                }
                highlight_options["fields"]["text.exact"] = {
                    "type": "plain",
                    "fragment_size": 100,
                    "number_of_fragments": 100,
                    "pre_tags": ["<mark>"],
                    "post_tags": ["</mark>"],
                }

        inner_hits = {"name": f"text_query_inner_{child_type}", "size": 10}

        if highlight_options:
            inner_hits["highlight"] = highlight_options

        child_query = []
        if value:
            child_query.append(build_fulltext_query(fields, value))

        if mlt_query:
            child_query.append(mlt_query)

        query = Q(
            "has_child",
            type=child_type,
            score_mode="max",
            query=Q("bool", should=child_query),
            inner_hits=inner_hits,
        )
        q_should.append(query)

    # Build parent document fulltext queries.
    if parent_fields and value:
        q_should.append(build_fulltext_query(parent_fields, value))

    if q_should:
        return Q("bool", should=q_should, minimum_should_match=1)
    return []


def build_has_child_filters(
    child_type: str, cd: CleanData
) -> list[QueryString]:
    """Builds Elasticsearch 'has_child' filters based on the given child type
    and CleanData.

    :param child_type: The type of child filter to build (e.g., "position").
    :param cd: The user input CleanedData.
    :return: A list of QueryString objects containing the 'has_child' filters.
    """

    queries_list = []
    if cd["type"] == SEARCH_TYPES.PEOPLE:
        if child_type == "position":
            selection_method = cd.get("selection_method", "")
            court = extend_selected_courts_with_child_courts(
                cd.get("court", "").split()
            )
            appointer = cd.get("appointer", "")
            if selection_method:
                queries_list.extend(
                    build_term_query(
                        "selection_method_id",
                        selection_method,
                    )
                )
            if court:
                queries_list.extend(build_term_query("court_exact.raw", court))
            if appointer:
                queries_list.extend(build_text_filter("appointer", appointer))

    if cd["type"] in [
        SEARCH_TYPES.RECAP,
        SEARCH_TYPES.DOCKETS,
        SEARCH_TYPES.RECAP_DOCUMENT,
    ]:
        if child_type == "recap_document":
            available_only = cd.get("available_only", "")
            description = cd.get("description", "")
            document_number = cd.get("document_number", "")
            attachment_number = cd.get("attachment_number", "")

            if available_only:
                queries_list.extend(
                    build_term_query(
                        "is_available",
                        available_only,
                    )
                )
            if description:
                queries_list.extend(
                    build_text_filter("description", description)
                )
            if document_number:
                queries_list.extend(
                    build_term_query("document_number", document_number)
                )
            if attachment_number:
                queries_list.extend(
                    build_term_query("attachment_number", attachment_number)
                )
            return queries_list

    if not queries_list:
        return []

    return [
        Q(
            "has_child",
            type=child_type,
            score_mode="max",
            query=reduce(operator.iand, queries_list),
            inner_hits={"name": f"filter_inner_{child_type}", "size": 10},
        )
    ]


def build_join_es_filters(cd: CleanData) -> List:
    """Builds join elasticsearch filters based on the CleanData object.

    :param cd: An object containing cleaned user data.
    :return: The list of Elasticsearch queries built.
    """

    queries_list = []
    if cd["type"] == SEARCH_TYPES.PEOPLE:
        # Build parent document filters.
        queries_list.extend(
            [
                Q("match", person_child="person"),
                *build_term_query("dob_state_id", cd.get("dob_state", "")),
                *build_term_query(
                    "political_affiliation_id",
                    cd.get("political_affiliation", "").split(),
                ),
                *build_daterange_query(
                    "dob", cd.get("born_before", ""), cd.get("born_after", "")
                ),
                *build_text_filter("dob_city", cd.get("dob_city", "")),
                *build_text_filter("name", cd.get("name", "")),
                *build_text_filter("school", cd.get("school", "")),
            ]
        )
        # Build position has child filter:
        queries_list.extend(build_has_child_filters("position", cd))

    if cd["type"] in [
        SEARCH_TYPES.RECAP,
        SEARCH_TYPES.DOCKETS,
        SEARCH_TYPES.RECAP_DOCUMENT,
    ]:
        queries_list.extend(
            [
                *build_term_query(
                    "court_id.raw",
                    extend_selected_courts_with_child_courts(
                        cd.get("court", "").split()
                    ),
                ),
                *build_text_filter("caseName", cd.get("case_name", "")),
                *build_term_query(
                    "docketNumber",
                    cd.get("docket_number", ""),
                    make_phrase=True,
                    slop=1,
                ),
                *build_text_filter("suitNature", cd.get("nature_of_suit", "")),
                *build_text_filter("cause", cd.get("cause", "")),
                *build_text_filter("assignedTo", cd.get("assigned_to", "")),
                *build_text_filter("referredTo", cd.get("referred_to", "")),
                *build_text_filter("party", cd.get("party_name", "")),
                *build_text_filter("attorney", cd.get("atty_name", "")),
                *build_daterange_query(
                    "dateFiled",
                    cd.get("filed_before", ""),
                    cd.get("filed_after", ""),
                ),
            ]
        )

    if cd["type"] == SEARCH_TYPES.OPINION:
        selected_stats = get_array_of_selected_fields(cd, "stat_")
        if len(selected_stats) and not cd.get("just_facets_query"):
            queries_list.extend(
                build_term_query(
                    "status.raw",
                    selected_stats,
                )
            )

        queries_list.extend(
            [
                *build_term_query(
                    "court_id.raw",
                    extend_selected_courts_with_child_courts(
                        cd.get("court", "").split()
                    ),
                ),
                *build_text_filter("caseName", cd.get("case_name", "")),
                *build_daterange_query(
                    "dateFiled",
                    cd.get("filed_before", ""),
                    cd.get("filed_after", ""),
                ),
                *build_term_query(
                    "docketNumber",
                    cd.get("docket_number", ""),
                    make_phrase=True,
                    slop=1,
                ),
                *build_text_filter("citation", cd.get("citation", "")),
                *build_text_filter("neutralCite", cd.get("neutral_cite", "")),
                *build_numeric_range_query(
                    "citeCount",
                    cd.get("cited_gt", ""),
                    cd.get("cited_lt", ""),
                ),
                *build_text_filter(
                    "judge",
                    cd.get("judge", ""),
                ),
                *build_term_query("id", cd.get("id", "").split()),
            ]
        )

    return queries_list


def add_highlighting_for_feed_query(s: Search, field: str) -> Search:
    """Add highlighting parameters for a feed query in ES.
    Although highlighting is not displayed in Feeds, this is required as an
    optimization to avoid returning the entire plain_text in RECAPDocuments
    or text in Opinions, which could be massive in some documents. This takes
    advantage of the no_match_size feature in highlighting to return only up to
    500 characters from the text field.

    :param s: Elasticsearch DSL Search object
    :param field: The field name for which highlighting is to be set.
    :return: The modified Elasticsearch DSL Search object with highlighting
    settings applied.
    """

    s = s.highlight(
        field,
        type=settings.ES_HIGHLIGHTER,
        fragment_size=500,
        no_match_size=settings.NO_MATCH_HL_SIZE,
        pre_tags=[f"<{SEARCH_HL_TAG}>"],
        post_tags=[f"</{SEARCH_HL_TAG}>"],
    )
    s = s.source(excludes=[field])

    return s


def build_search_feed_query(
    search_query: Search,
    cd: CleanData,
    jurisdiction: bool,
    exclude_docs_for_empty_field: str,
) -> Search:
    """Builds a search query for the feed based on cd and jurisdiction flag.

    :param search_query:  Elasticsearch DSL Search object
    :param cd: The query CleanedData
    :param jurisdiction: Whether to perform a jurisdiction query with all the
    child opinions.
    :param exclude_docs_for_empty_field: Field that should not be empty for a
    document to be included
    :return: An Elasticsearch DSL Search object containing the feed query.
    """

    hl_field = "text"
    if cd["type"] == SEARCH_TYPES.RECAP:
        hl_field = "plain_text"
    s, join_query = build_es_base_query(search_query, cd)
    if jurisdiction or cd["type"] == SEARCH_TYPES.RECAP:
        # An Opinion Jurisdiction feed or RECAP Search displays child documents
        # Eliminate items that lack the ordering field and apply highlighting
        # to create a snippet for the plain_text or text fields.
        s = build_child_docs_query(
            join_query,
            cd=cd,
            exclude_docs_for_empty_field=exclude_docs_for_empty_field,
        )
        s = search_query.query(s)
        s = add_highlighting_for_feed_query(s, hl_field)
    return s


def do_es_feed_query(
    search_query: Search,
    cd: CleanData,
    rows: int = 20,
    jurisdiction: bool = False,
    exclude_docs_for_empty_field: str = "",
) -> Response | list:
    """Execute an Elasticsearch query for podcasts.

    :param search_query: Elasticsearch DSL Search object
    :param cd: The query CleanedData
    :param rows: Number of rows (items) to be retrieved in the response
    :param jurisdiction: Whether to perform a jurisdiction query with all the
    child opinions.
    :param exclude_docs_for_empty_field: Field that should not be empty for a
    document to be included
    :return: The Elasticsearch DSL response.
    """

    s = build_search_feed_query(
        search_query, cd, jurisdiction, exclude_docs_for_empty_field
    )
    s = s.sort(build_sort_results(cd))
    response = s.extra(from_=0, size=rows).execute()
    if cd["type"] == SEARCH_TYPES.OPINION:
        # Merge the text field for Opinions.
        if not jurisdiction:
            limit_inner_hits(cd, response, cd["type"])

    set_results_highlights(response, cd["type"])
    return response


def nullify_query_score(query: Query) -> Query:
    """Nullify the scoring of a query.
    This function modifies the scoring of the given query to always return zero,
    which is useful for prioritizing a score set upstream or downstream.

    :param query: The ES Query object to be modified.
    :return: The modified Query object with a script score that always
    returns zero.
    """

    query = Q(
        "function_score",
        query=query,
        script_score={
            "script": {
                "source": """ return 0; """,
            },
        },
        # Replace the original score with the one computed by the script
        boost_mode="replace",
    )
    return query


def apply_custom_score_to_parent_query(
    cd: CleanData, query: Query, api_version: Literal["v3", "v4"] | None = None
) -> Query:
    """Apply a custom function score to a main document.

    :param cd: The query CleanedData
    :param query: The ES Query object to be modified.
    :param api_version: Optional, the request API version.
    :return: The function_score query contains the base query, applied when
    child_order is used.
    """
    child_order_by = get_child_sorting_key(cd, api_version)
    valid_child_order_by = child_order_by and all(child_order_by)
    match cd["type"]:
        case SEARCH_TYPES.RECAP | SEARCH_TYPES.DOCKETS if valid_child_order_by:
            sort_field, order = child_order_by
            if sort_field == "entry_date_filed":
                # It applies a function score to the parent query to nullify
                # the parent score (sets it to 0) to prioritize child documents
                # sorting criteria. This will ensure that dockets without
                # documents come last on results.
                query = nullify_query_score(query)
            elif sort_field == "dateFiled" and api_version:
                # Applies a custom function score to sort Dockets based on
                # their dateFiled field. This serves as a workaround to enable
                # the use of the  search_after cursor for pagination on
                # documents with a None dateFiled.
                query = build_custom_function_score_for_date(
                    query, child_order_by, default_score=0
                )
        case SEARCH_TYPES.RECAP_DOCUMENT if valid_child_order_by:
            sort_field, order = child_order_by
            if sort_field in ["dateFiled", "entry_date_filed"] and api_version:
                # Applies a custom function score to sort RECAPDocuments based
                # on their docket dateFiled or entry_date_filed field. This
                # serves as a workaround to enable the use of the  search_after
                # cursor for pagination on documents with a None dateFiled.
                query = build_custom_function_score_for_date(
                    query, child_order_by, default_score=0
                )
    return query


def build_full_join_es_queries(
    cd: CleanData,
    child_query_fields: dict[str, list[str]],
    parent_query_fields: list[str],
    mlt_query: Query | None = None,
    child_highlighting: bool = True,
    api_version: Literal["v3", "v4"] | None = None,
) -> tuple[QueryString | list, QueryString | None]:
    """Build a complete Elasticsearch query with both parent and child document
      conditions.

    :param cd: The query CleanedData
    :param child_query_fields: A dictionary mapping child fields document type.
    :param parent_query_fields: A list of fields for the parent document.
    :param mlt_query: the More Like This Query object.
    :param child_highlighting: Whether highlighting should be enabled in child docs.
    :param api_version: Optional, the request API version.
    :return: An Elasticsearch QueryString object.
    """

    q_should = []
    match cd["type"]:
        case (
            SEARCH_TYPES.RECAP
            | SEARCH_TYPES.DOCKETS
            | SEARCH_TYPES.RECAP_DOCUMENT
        ):
            child_type = "recap_document"
        case SEARCH_TYPES.OPINION:
            child_type = "opinion"

    join_query = None
    if cd["type"] in [
        SEARCH_TYPES.RECAP,
        SEARCH_TYPES.DOCKETS,
        SEARCH_TYPES.RECAP_DOCUMENT,
        SEARCH_TYPES.OPINION,
    ]:
        # Build child filters.
        child_filters = build_has_child_filters(child_type, cd)
        # Copy the original child_filters before appending parent fields.
        # For its use later in the parent filters.
        child_filters_original = deepcopy(child_filters)
        # Build child text query.
        child_fields = child_query_fields[child_type]
        child_text_query = build_fulltext_query(
            child_fields, cd.get("q", ""), only_queries=True
        )

        if mlt_query:
            child_text_query.append(mlt_query)

        # Build parent filters.
        parent_filters = build_join_es_filters(cd)
        parties_filters = [
            query
            for query in parent_filters
            if isinstance(query, QueryString)
            and query.fields[0] in ["party", "attorney"]
        ]
        has_parent_parties_filter = build_has_parent_parties_query(
            parties_filters
        )
        # If parent filters, extend into child_filters.
        if parent_filters:
            # Removes the party and attorney filter if they were provided because
            # those fields are not part of the RECAPDocument mapping.
            child_filters.extend(
                [
                    query
                    for query in parent_filters
                    if not isinstance(query, QueryString)
                    or query.fields[0] not in ["party", "attorney"]
                ]
            )
            if parties_filters:
                # If party filters were provided, append a has_parent query
                # with the party filters included to match only child documents
                # whose parents match the party filters.
                child_filters.append(has_parent_parties_filter)

        # Build the child query based on child_filters and child child_text_query
        match child_filters, child_text_query:
            case [], []:
                pass
            case [], _:
                join_query = Q(
                    "bool",
                    should=child_text_query,
                    minimum_should_match=1,
                )
            case _, []:
                join_query = Q(
                    "bool",
                    filter=child_filters,
                )
            case _, _:
                join_query = Q(
                    "bool",
                    filter=child_filters,
                    should=child_text_query,
                    minimum_should_match=1,
                )

        _, query_hits_limit = get_child_top_hits_limit(cd, cd["type"])
        has_child_query = None
        if child_text_query or child_filters:
            hl_fields = (
                (
                    SEARCH_OPINION_CHILD_HL_FIELDS
                    if cd["type"] == SEARCH_TYPES.OPINION
                    else SEARCH_RECAP_CHILD_HL_FIELDS
                )
                if child_highlighting
                else SEARCH_RECAP_CHILD_EXCLUDE_FIELDS
            )
            has_child_query = build_has_child_query(
                join_query,
                child_type,
                query_hits_limit,
                hl_fields,
                get_child_sorting_key(cd, api_version),
                child_highlighting=child_highlighting,
                api_version=api_version,
            )

        if parties_filters and not has_child_query:
            # If party filters were provided and there is no
            # has_child_query, build a has_child query including
            # has_parent_parties_filter to match only child documents whose
            # parents match the party filters.
            has_child_query = build_has_child_query(
                has_parent_parties_filter,
                "recap_document",
                query_hits_limit,
                SEARCH_RECAP_CHILD_HL_FIELDS,
                get_child_sorting_key(cd, api_version),
                api_version=api_version,
            )

        if has_child_query:
            q_should.append(has_child_query)

        # Build the parent filter and text queries.
        string_query = build_fulltext_query(
            parent_query_fields, cd.get("q", ""), only_queries=True
        )

        # If child filters are set, add a has_child query as a filter to the
        # parent query to exclude results without matching children.
        if child_filters_original:
            parent_filters.append(
                Q(
                    "has_child",
                    type=child_type,
                    score_mode="max",
                    query=Q("bool", filter=child_filters_original),
                )
            )
        parent_query = None
        default_parent_filter = (
            Q("match", cluster_child="opinion_cluster")
            if child_type == "opinion"
            else Q("match", docket_child="docket")
        )
        match parent_filters, string_query:
            case [], []:
                pass
            case [], _:
                parent_query = Q(
                    "bool",
                    filter=default_parent_filter,
                    should=string_query,
                    minimum_should_match=1,
                )
            case _, []:
                parent_filters.extend([default_parent_filter])
                parent_query = Q(
                    "bool",
                    filter=parent_filters,
                )
            case _, _:
                parent_filters.extend([default_parent_filter])
                parent_query = Q(
                    "bool",
                    filter=parent_filters,
                    should=string_query,
                    minimum_should_match=1,
                )
        if parent_query:
            parent_query = apply_custom_score_to_parent_query(
                cd, parent_query, api_version
            )
            q_should.append(parent_query)

    if not q_should:
        return [], join_query

    return (
        Q(
            "bool",
            should=q_should,
        ),
        join_query,
    )


def limit_inner_hits(
    get_params: QueryDict | CleanData,
    results: Page | Response,
    search_type: str,
) -> None:
    """Limit inner hits of has_child query results.

    :param get_params: The user search params.
    :param results: The Page or Response object containing search results.
    :param search_type: The search type to perform.
    :return: None, the function updates the results in place.
    """

    hits_limit, _ = get_child_top_hits_limit(get_params, search_type)
    match search_type:
        case SEARCH_TYPES.OPINION:
            child_type = "opinion"
        case (
            SEARCH_TYPES.RECAP
            | SEARCH_TYPES.DOCKETS
            | SEARCH_TYPES.RECAP_DOCUMENT
        ):
            child_type = "recap_document"
        case _:
            return

    for result in results:
        result["child_docs"] = []
        result["child_remaining"] = False
        result["child_remaining_query_id"] = False
        try:
            inner_hits = [
                hit
                for hit in result.meta["inner_hits"][
                    f"filter_query_inner_{child_type}"
                ]["hits"]["hits"]
            ]
        except KeyError:
            continue

        docket_id_query = re.search(r"docket_id:\d+", get_params.get("q", ""))
        count_hits = len(inner_hits)
        if count_hits > hits_limit:
            result["child_docs"] = inner_hits[:hits_limit]
            if docket_id_query:
                result["child_remaining_query_id"] = True
            else:
                result["child_remaining"] = True
        else:
            result["child_docs"] = inner_hits


def get_child_top_hits_limit(
    search_params: QueryDict | CleanData, search_type: str
) -> tuple[int, int]:
    """Get the frontend and query hit limits for child documents.

    :param search_params: Either a QueryDict or CleanData object containing the
    search parameters.
    :param search_type: Elasticsearch DSL Search object
    :return: A two tuple containing the limit for frontend hits, the limit for
     query hits.
    """

    frontend_hits_limit = settings.CHILD_HITS_PER_RESULT
    # Increase the CHILD_HITS_PER_RESULT value by 1. This is done to determine
    # whether there are more than CHILD_HITS_PER_RESULT results, which would
    # trigger the "View Additional Results" button on the frontend.
    query_hits_limit = settings.CHILD_HITS_PER_RESULT + 1

    if search_type not in [SEARCH_TYPES.RECAP, SEARCH_TYPES.DOCKETS]:
        return frontend_hits_limit, query_hits_limit

    if search_type == SEARCH_TYPES.DOCKETS:
        frontend_hits_limit = 1

    docket_id_query = re.search(r"docket_id:\d+", search_params.get("q", ""))
    if docket_id_query:
        frontend_hits_limit = settings.VIEW_MORE_CHILD_HITS
        query_hits_limit = settings.VIEW_MORE_CHILD_HITS + 1

    return frontend_hits_limit, query_hits_limit


def do_count_query(
    search_query: Search,
) -> int | None:
    """Execute an Elasticsearch count query and catch errors.
    :param search_query: Elasticsearch DSL Search object.
    :return: The results count.
    """
    try:
        total_results = search_query.count()
    except (TransportError, ConnectionError, RequestError) as e:
        logger.warning(
            f"Error on count query request: {search_query.to_dict()}"
        )
        logger.warning(f"Error was: {e}")
        total_results = None
    return total_results


def merge_opinion_and_cluster(results: Page | dict) -> None:
    """Merges the fields from the opinion document with the best score into
    the search results.
    :param results: A Page object containing the search results to be modified.
    :return: None, the function modifies the search results object in place.
    """
    for result in results:
        opinion = result["child_hits"][0]["_source"]
        result["cluster_id"] = result["id"]
        result["id"] = opinion["id"]
        result["author_id"] = opinion["author_id"]
        result["type"] = opinion["type"]
        result["download_url"] = opinion["download_url"]
        result["local_path"] = opinion["local_path"]
        result["text"] = opinion["text"]
        result["per_curiam"] = opinion["per_curiam"]
        result["cites"] = opinion["cites"]
        result["joined_by_ids"] = opinion["joined_by_ids"]
        result["court_exact"] = opinion["joined_by_ids"]
        result["status_exact"] = result["status"]


async def get_related_clusters_with_cache_and_es(
    search: Search,
    cluster: OpinionCluster,
    request: HttpRequest,
) -> tuple[Page | list, list[int], dict[str, str]]:
    """Retrieve related opinion clusters from ES or cache.

    :param search: The ES Search object.
    :param cluster: The current OpinionCluster.
    :param request: The HttpRequest object.
    :return: A three tuple containing a Page containing opinion clusters or an
    empty list. A list containing the cluster sub opinions ids. A dic containing
    the url_search_params.
    """

    # By default, all statuses are included. Retrieve the PRECEDENTIAL_STATUS
    # attributes (since they're indexed in ES) instead of the NAMES values.
    available_statuses = [status[0] for status in PRECEDENTIAL_STATUS.NAMES]
    url_search_params = {f"stat_{v}": "on" for v in available_statuses}
    search_params: CleanData = {}
    # Opinions that belong to the targeted cluster
    sub_opinion_ids = cluster.sub_opinions.values_list("pk", flat=True)
    sub_opinion_pks = [pk async for pk in sub_opinion_ids]
    if is_bot(request) or not sub_opinion_pks:
        # If it is a bot or lacks sub-opinion IDs, return empty results
        return [], [], url_search_params

    # Use cache if enabled
    cache = caches["db_cache"]
    mlt_cache_key = f"mlt-cluster-es:{cluster.pk}"
    related_clusters = (
        await cache.aget(mlt_cache_key) if settings.RELATED_USE_CACHE else None
    )

    if settings.RELATED_FILTER_BY_STATUS:
        # Filter results by status (e.g., Precedential)
        # Update URL parameters accordingly
        search_params[
            f"stat_{PRECEDENTIAL_STATUS.get_status_value(settings.RELATED_FILTER_BY_STATUS)}"
        ] = True
        url_search_params = {
            f"stat_{PRECEDENTIAL_STATUS.get_status_value(settings.RELATED_FILTER_BY_STATUS)}": "on"
        }

    if related_clusters is None:
        sub_opinion_queries = ",".join(str(pk) for pk in sub_opinion_pks)
        search_params["q"] = f"related:{sub_opinion_queries}"
        search_params["type"] = SEARCH_TYPES.OPINION
        query_dict = QueryDict("", mutable=True)
        query_dict.update(search_params)
        search_query, child_docs_count_query, _ = await sync_to_async(
            build_es_main_query
        )(search, search_params)
        hits, _, error, total_query_results, _ = await sync_to_async(
            fetch_es_results
        )(
            query_dict,
            search_query,
            child_docs_count_query,
            1,
            settings.RELATED_COUNT,
        )
        if error:
            return [], [], url_search_params

        @sync_to_async
        def paginate_related_clusters(total_results: int, results: Response):
            paginator = ESPaginator(
                total_results, results, settings.RELATED_COUNT
            )
            try:
                return paginator.page(1)
            except EmptyPage:
                return paginator.page(paginator.num_pages)

        related_clusters = await paginate_related_clusters(
            total_query_results, hits
        )

        await cache.aset(
            mlt_cache_key, related_clusters, settings.RELATED_CACHE_TIMEOUT
        )
    return related_clusters, sub_opinion_pks, url_search_params


def make_es_stats_variable(
    search_form: SearchForm,
    results: Page | Response,
) -> list[BoundField]:
    """Create a useful facet variable for use in a template

    :param search_form: The form displayed in the user interface
    :param results: The Page or Response containing the results to add the
    status aggregations.
    """

    facet_fields = []
    try:
        if isinstance(results, Page):
            aggregations = results.paginator.aggregations.to_dict()  # type: ignore
            buckets = aggregations["status"]["buckets"]
        else:
            buckets = results.aggregations.status.buckets
        facet_values = {group["key"]: group["doc_count"] for group in buckets}
    except (KeyError, AttributeError):
        facet_values = {}

    for field in search_form:
        if not field.html_name.startswith("stat_"):
            continue

        try:
            count = facet_values[field.html_name.replace("stat_", "")]
        except KeyError:
            # Happens when a field is iterated on that doesn't exist in the
            # facets variable
            count = 0

        field.count = count
        facet_fields.append(field)
    return facet_fields


def fetch_all_search_results(
    fetch_method: Callable, initial_response: Response, *args
) -> list[Hit]:
    """Fetches all search results based on a given search method and an
    initial response. It retrieves all the search results that exceed the
    initial batch size by iteratively calling the provided fetch method with
    the necessary pagination parameters.

    :param fetch_method: A callable that executes the search query.
    :param initial_response: The initial ES Response object.
    :param args: Additional arguments to pass to the fetch method.

    :return: A list of `Hit` objects representing all search results.
    """

    all_search_hits = []
    all_search_hits.extend(initial_response.hits)
    total_hits = initial_response.hits.total.value
    results_returned = len(initial_response.hits.hits)
    if total_hits > settings.ELASTICSEARCH_PAGINATION_BATCH_SIZE:
        documents_retrieved = results_returned
        search_after = initial_response.hits[-1].meta.sort
        while True:
            response = fetch_method(*args, search_after=search_after)
            if not response:
                break

            all_search_hits.extend(response.hits)
            results_returned = len(response.hits.hits)
            documents_retrieved += results_returned
            # Check if all results have been retrieved. If so break the loop
            # Otherwise, increase search_after.
            if documents_retrieved >= total_hits or results_returned == 0:
                break
            else:
                search_after = response.hits[-1].meta.sort
    return all_search_hits


def do_es_api_query(
    search_query: Search,
    cd: CleanData,
    highlighting_fields: dict[str, int],
    hl_tag: str,
    api_version: Literal["v3", "v4"],
) -> tuple[Search, Query | None]:
    """Build an ES query for its use in the Search API and Webhooks.

    :param search_query: Elasticsearch DSL Search object.
    :param cd: The query CleanedData
    :param highlighting_fields: A dictionary mapping field names to fragment
    sizes for highlighting.
    :param hl_tag: The HTML tag to use for highlighting matched fragments.
    :param api_version: The request API version.
    :return: A two-tuple, the Elasticsearch search query object and an ES
    Query for child documents, or None if there is no need to query
    child documents.
    """

    child_docs_query = None
    s, join_query = build_es_base_query(
        search_query, cd, cd["highlight"], api_version
    )
    extra_options: dict[str, dict[str, Any]] = {}
    if api_version == "v3":
        # Build query parameters for the ES V3 Search API endpoints.
        # V3 endpoints display child documents. Here, the child documents query
        # is retrieved, and extra parameters like highlighting, field exclusion,
        # and sorting are set.
        # Note that in V3 Case Law Search, opinions are collapsed by cluster_id
        # meaning that only one result per cluster is shown.
        s = build_child_docs_query(
            join_query,
            cd=cd,
        )
        main_query = search_query.query(s)
        highlight_options, fields_to_exclude = build_highlights_dict(
            highlighting_fields, hl_tag
        )
        main_query = main_query.source(excludes=fields_to_exclude)
        extra_options["highlight"] = highlight_options
        if cd["type"] == SEARCH_TYPES.OPINION:
            extra_options.update(
                {
                    "collapse": {
                        "field": "cluster_id",
                    }
                }
            )
        main_query = main_query.extra(**extra_options)
        main_query = main_query.sort(
            build_sort_results(cd, api_version=api_version)
        )
    else:
        child_docs_query = build_child_docs_query(
            join_query,
            cd=cd,
        )
        # Build query params for the ES V4 Search API endpoints.
        if cd["type"] == SEARCH_TYPES.RECAP_DOCUMENT:
            # The RECAP_DOCUMENT search type returns only child documents.
            # Here, the child documents query is retrieved, highlighting and
            # field exclusion are set.

            s = apply_custom_score_to_parent_query(
                cd, child_docs_query, api_version
            )
            main_query = search_query.query(s)
            highlight_options, fields_to_exclude = build_highlights_dict(
                SEARCH_RECAP_CHILD_HL_FIELDS, hl_tag
            )
            main_query = main_query.source(excludes=fields_to_exclude)
            if cd["highlight"]:
                extra_options["highlight"] = highlight_options
                main_query = main_query.extra(**extra_options)
        else:
            # DOCKETS and RECAP search types. Use the same query parameters as
            # in the frontend. Only switch highlighting according to the user
            # request.
            main_query = s
            if cd["highlight"]:
                main_query = add_es_highlighting(s, cd)
    return main_query, child_docs_query


def build_cardinality_count(
    base_query: Search, query: Query, unique_field: str
) -> Search:
    """Build an Elasticsearch cardinality aggregation.
    This aggregation estimates the count of unique documents based on the
    specified unique field. The precision_threshold, set by
    ELASTICSEARCH_CARDINALITY_PRECISION, determines the point at which the
    count begins to trade accuracy for performance.

    :param base_query: The Elasticsearch DSL Search object.
    :param query: The ES Query object to perform the count query.
    :param unique_field: The field name on which the cardinality aggregation
    will be based to estimate uniqueness.

    :return: The ES cardinality aggregation query.
    """

    search_query = base_query.query(query)
    search_query.aggs.bucket(
        "unique_documents",
        "cardinality",
        field=unique_field,
        precision_threshold=settings.ELASTICSEARCH_CARDINALITY_PRECISION,
    )
    return search_query.extra(size=0, track_total_hits=True)


def do_collapse_count_query(main_query: Search, query: Query) -> int | None:
    """Execute an Elasticsearch count query for queries that uses collapse.
    Uses a query with aggregation to determine the number of unique opinions
    based on the 'cluster_id' field.

    :param main_query: The Elasticsearch DSL Search object.
    :param query: The ES Query object to perform the count query.
    :return: The results count.
    """

    search_query = build_cardinality_count(main_query, query, "cluster_id")
    try:
        total_results = (
            search_query.execute().aggregations.unique_documents.value
        )
    except (TransportError, ConnectionError, RequestError) as e:
        logger.warning(
            f"Error on count query request: {search_query.to_dict()}"
        )
        logger.warning(f"Error was: {e}")
        total_results = None
    return total_results
