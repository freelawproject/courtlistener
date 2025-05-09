import datetime
import logging
import operator
import re
import time
import traceback
from collections import defaultdict
from collections.abc import Callable
from copy import deepcopy
from dataclasses import fields
from functools import reduce, wraps
from typing import Any, Literal

from asgiref.sync import async_to_sync
from django.conf import settings
from django.core.paginator import Page
from django.db.models import Case, QuerySet, TextField, When
from django.db.models import Q as QObject
from django.db.models.functions import Substr
from django.forms.boundfield import BoundField
from django.http.request import QueryDict
from django.utils.html import strip_tags
from django_elasticsearch_dsl.search import Search
from elasticsearch.exceptions import ApiError, RequestError, TransportError
from elasticsearch_dsl import A, MultiSearch, Q
from elasticsearch_dsl import Search as SearchDSL
from elasticsearch_dsl.aggs import DateHistogram
from elasticsearch_dsl.query import Query, QueryString, Range
from elasticsearch_dsl.response import Hit, Response
from elasticsearch_dsl.utils import AttrDict, AttrList

from cl.audio.models import Audio
from cl.custom_filters.templatetags.text_filters import html_decode
from cl.lib.courts import lookup_child_courts_cache
from cl.lib.date_time import midnight_pt
from cl.lib.string_utils import trunc
from cl.lib.types import (
    ApiPositionMapping,
    BasePositionMapping,
    CleanData,
    EsJoinQueries,
    EsMainQueries,
    ESRangeQueryParams,
)
from cl.lib.utils import (
    check_for_proximity_tokens,
    check_query_for_disallowed_wildcards,
    check_unbalanced_parenthesis,
    check_unbalanced_quotes,
    cleanup_main_query,
    get_array_of_selected_fields,
    map_to_docket_entry_sorting,
    perform_special_character_replacements,
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
    SEARCH_MLT_OPINION_QUERY_FIELDS,
    SEARCH_OPINION_HL_FIELDS,
    SEARCH_OPINION_QUERY_FIELDS,
    SEARCH_ORAL_ARGUMENT_ES_HL_FIELDS,
    SEARCH_ORAL_ARGUMENT_QUERY_FIELDS,
    SEARCH_PEOPLE_CHILD_QUERY_FIELDS,
    SEARCH_PEOPLE_PARENT_QUERY_FIELDS,
    SEARCH_RECAP_CHILD_HL_FIELDS,
    SEARCH_RECAP_CHILD_QUERY_FIELDS,
    SEARCH_RECAP_HL_FIELDS,
    SEARCH_RECAP_PARENT_QUERY_FIELDS,
    api_child_highlight_map,
    cardinality_query_unique_ids,
    date_decay_relevance_types,
    recap_boosts_es,
)
from cl.search.exception import (
    BadProximityQuery,
    DisallowedWildcardPattern,
    ElasticBadRequestError,
    QueryType,
    UnbalancedParenthesesQuery,
    UnbalancedQuotesQuery,
)
from cl.search.forms import SearchForm
from cl.search.models import SEARCH_TYPES, Court, Opinion, RECAPDocument

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


class CSVSerializableDocumentMixin:
    @classmethod
    def get_csv_headers(cls) -> list[str]:
        """
        Returns a list of strings representing the headers for a CSV file.

        This method defines the column headers for a CSV representation of the
        data associated with this class.

        :return: A list of strings, where each string is a column header.
        """
        raise NotImplementedError(
            "Subclass must implement get_csv_headers method"
        )

    @classmethod
    def get_csv_transformations(cls) -> dict[str, Callable[..., Any]]:
        """
        Generates a dictionary of transformation functions for CSV export.

        This method defines how specific fields in a data structure should be
        transformed before being written to a CSV file. It covers
        transformations for various fields, including those from list of fields
        with highlights, file paths, URLs, and renamed fields.

        :return: A dictionary where keys are field names and values are lambda
        functions that define the transformations.
        """
        raise NotImplementedError(
            "Subclass must implement get_csv_transformations method"
        )


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
        assert relation in allowed_relations, (
            f"'{relation}' is not an allowed relation."
        )
        params["relation"] = relation

    return [Q("range", **{field: params})]


def build_daterange_query(
    field: str,
    before: datetime.date | str,
    after: datetime.date | str,
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
        if isinstance(after, datetime.date):
            params["gte"] = f"{after.isoformat()}T00:00:00Z"
        if isinstance(before, datetime.date):
            params["lte"] = f"{before.isoformat()}T23:59:59Z"
        if relation is not None:
            allowed_relations = ["INTERSECTS", "CONTAINS", "WITHIN"]
            assert relation in allowed_relations, (
                f"'{relation}' is not an allowed relation."
            )
            params["relation"] = relation

    if params:
        return [Q("range", **{field: params})]

    return []


async def build_more_like_this_query(related_ids: list[str]) -> Query:
    """Build an ES "more like this" query based on related Opinion IDs.

    :param related_ids: A list of related Opinion IDs to build the query on.
    :return: An ES query object with "more like this" query and
    exclusions for specific opinion clusters.
    """

    opinion_cluster_pairs = [
        opinion_pair
        for opinion_id in related_ids
        if (
            opinion_pair := await Opinion.objects.filter(pk=opinion_id)
            .values("pk", "cluster_id")
            .afirst()
        )
    ]
    unique_clusters = {pair["cluster_id"] for pair in opinion_cluster_pairs}

    document_list = [
        {
            "_id": f"o_{pair['pk']}",
            "routing": pair["cluster_id"],
            # Important to match documents in the production cluster
        }
        for pair in opinion_cluster_pairs
    ] or [
        {"_id": f"o_{pk}"} for pk in related_ids
    ]  # Fallback in case IDs are not found in the database.
    # The user might have provided non-existent Opinion IDs.
    # This ensures that the query does not raise an error and instead returns
    # no results.

    more_like_this_fields = SEARCH_MLT_OPINION_QUERY_FIELDS.copy()
    mlt_query = Q(
        "more_like_this",
        fields=more_like_this_fields,
        like=document_list,
        min_term_freq=settings.RELATED_MLT_MINTF,
        max_query_terms=settings.RELATED_MLT_MAXQT,
        min_word_length=settings.RELATED_MLT_MINWL,
        max_word_length=settings.RELATED_MLT_MAXWL,
        max_doc_freq=settings.RELATED_MLT_MAXDF,
        analyzer="search_analyzer_exact",
    )
    # Exclude opinion clusters to which the related IDs to query belong.
    cluster_ids_list = list(unique_clusters)
    exclude_cluster_ids = [Q("terms", cluster_id=cluster_ids_list)]
    bool_query = Q("bool", must=[mlt_query], must_not=exclude_cluster_ids)
    return bool_query


def make_es_boost_list(fields: dict[str, float]) -> list[str]:
    """Constructs a list of Elasticsearch fields with their corresponding
    boost values.

    :param fields: A dictionary where keys are field names and values are
    the corresponding boost values.
    :return: A list of Elasticsearch fields with boost values formatted as 'field_name^boost_value'.
    """
    return [f"{k}^{v}" for k, v in fields.items()]


def is_case_name_query(query_value: str) -> bool:
    """Determines if the given query value is likely a case name query.

    :param query_value: The search query to check.
    :return: True if the query appears to be a case name, otherwise False.
    """

    vs_query = any(
        [
            " v " in query_value,
            " v. " in query_value,
            " vs. " in query_value,
            " vs " in query_value,
        ]
    )
    query_lower = query_value.lower()
    in_re_query = query_lower.startswith("in re ")
    matter_of_query = query_lower.startswith("matter of ")
    ex_parte_query = query_lower.startswith("ex parte ")

    return any([vs_query, in_re_query, matter_of_query, ex_parte_query])


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
        SEARCH_TYPES.OPINION,
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
        if is_case_name_query(query):
            qf.update({"caseName.exact": 75})

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
        raise UnbalancedParenthesesQuery(query_type)
    if check_unbalanced_quotes(value):
        raise UnbalancedQuotesQuery(query_type)
    if check_for_proximity_tokens(value):
        raise BadProximityQuery(query_type)


def build_fulltext_query(
    fields: list[str], value: str, only_queries=False
) -> QueryString | list:
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
        # Used for the phrase query_string, no conjunctions appended.
        query_value = cleanup_main_query(value)
        # To enable the search of each term in the query across multiple fields
        # it's necessary to include an "AND" conjunction between each term.
        # https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-query-string-query.html#query-string-multi-field
        # Used for the best_fields query_string.

        query_value_with_conjunctions = append_query_conjunctions(query_value)
        q_should = []
        # If it looks like a case name, we are boosting a match query
        if is_case_name_query(query_value) and '"' not in query_value:
            q_should.append(
                Q(
                    "match_phrase",
                    **{
                        "caseName.exact": {
                            "query": query_value,
                            "boost": 2,
                            "slop": 1,
                        }
                    },
                )
            )

        q_should.extend(
            [
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
        )

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
    NOTE: Use it only when you want an exact match, avoid using this with text fields
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
        return [
            Q(
                "match_phrase",
                **{
                    field: {
                        "query": value,
                        "slop": slop,
                        "analyzer": "search_analyzer_exact",
                    }
                },
            )
        ]

    if isinstance(value, list):
        value = list(filter(None, value))
        return [Q("terms", **{field: value})]

    return [Q("term", **{field: value})]


def build_text_filter(field: str, value: str) -> list:
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
            if check_query_for_disallowed_wildcards(value):
                raise DisallowedWildcardPattern(QueryType.FILTER)
            value = perform_special_character_replacements(value)
        return [
            Q(
                "query_string",
                query=value,
                fields=[field],
                default_operator="AND",
                quote_field_suffix=".exact",
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

    if not toggle_sorting or order_by is None:
        return order_by

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
    return ",".join(toggle_sort_components)


def build_sort_results(
    cd: CleanData,
    toggle_sorting: bool = False,
    api_version: Literal["v3", "v4"] | None = None,
) -> dict:
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
        "name_reverse desc": {"name_reverse": {"order": "desc"}},
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

    if api_version == "v3":
        # Override entry_date_filed sorting keys in the V3 RECAP Search API.
        # Since no function score is required to sort documents because no
        # has_child query is used.
        order_by_map["entry_date_filed desc"] = {
            "entry_date_filed": {"order": "desc"}
        }
        order_by_map["entry_date_filed asc"] = {
            "entry_date_filed": {"order": "asc"}
        }

    require_v4_function_score = cd["type"] in [
        SEARCH_TYPES.RECAP,
        SEARCH_TYPES.DOCKETS,
        SEARCH_TYPES.RECAP_DOCUMENT,
        SEARCH_TYPES.PEOPLE,
        SEARCH_TYPES.ORAL_ARGUMENT,
    ]

    if api_version == "v4" and require_v4_function_score:
        # Override dateFiled sorting keys in V4 RECAP Search API to work
        # alongside the custom function score for sorting by dateFiled.
        order_by_map["dateFiled desc"] = {"_score": {"order": "desc"}}
        order_by_map["dateFiled asc"] = {"_score": {"order": "desc"}}
        order_by_map["dob desc,name_reverse asc"] = {
            "_score": {"order": "desc"},
            "name_reverse": {"order": "asc"},
        }
        order_by_map["dob asc,name_reverse asc"] = {
            "_score": {"order": "desc"},
            "name_reverse": {"order": "asc"},
        }
        order_by_map["dod desc,name_reverse asc"] = {
            "_score": {"order": "desc"},
            "name_reverse": {"order": "asc"},
        }

        order_by_map["dateArgued desc"] = {"_score": {"order": "desc"}}
        order_by_map["dateArgued asc"] = {"_score": {"order": "desc"}}

    if toggle_sorting and api_version == "v4" and require_v4_function_score:
        # Override the sorting keys in V4 RECAP Search API when toggle_sorting
        # is True for backward cursor pagination based on fields that use a custom
        # function score.
        order_by_map["entry_date_filed asc"] = {"_score": {"order": "asc"}}
        order_by_map["entry_date_filed desc"] = {"_score": {"order": "asc"}}
        order_by_map["dateFiled desc"] = {"_score": {"order": "asc"}}
        order_by_map["dateFiled asc"] = {"_score": {"order": "asc"}}

        order_by_map["dob asc,name_reverse desc"] = {
            "_score": {"order": "asc"},
            "name_reverse": {"order": "desc"},
        }
        order_by_map["dob desc,name_reverse desc"] = {
            "_score": {"order": "asc"},
            "name_reverse": {"order": "desc"},
        }
        order_by_map["dod asc,name_reverse desc"] = {
            "_score": {"order": "asc"},
            "name_reverse": {"order": "desc"},
        }

        order_by_map["dateArgued desc"] = {"_score": {"order": "asc"}}
        order_by_map["dateArgued asc"] = {"_score": {"order": "asc"}}

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


def get_function_score_sorting_key(
    cd: CleanData, api_version: Literal["v3", "v4"] | None = None
) -> tuple[str, str]:
    """Given cleaned data, find the order_by value and return a key to use for
    computing a custom score within build_custom_function_score_for_date.

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
                "dob desc,name_reverse asc": ("dob", "desc"),
                "dob asc,name_reverse asc": ("dob", "asc"),
                "dod desc,name_reverse asc": ("dod", "desc"),
                "dateArgued desc": ("dateArgued", "desc"),
                "dateArgued asc": ("dateArgued", "asc"),
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
    unique_courts.update(lookup_child_courts_cache(list(unique_courts)))
    return list(unique_courts)


def build_es_plain_filters(cd: CleanData) -> list:
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
                "docketNumber.exact",
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
            build_text_filter("caseName.exact", cd.get("case_name", ""))
        )
        # Build judge terms filter
        queries_list.extend(build_text_filter("judge", cd.get("judge", "")))

    return queries_list


def build_highlights_dict(
    highlighting_fields: dict[str, int] | None,
    hl_tag: str,
    highlighting: bool = True,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Builds a dictionary for ES highlighting options and a list of fields to
    exclude from the _source.

    :param highlighting_fields: A dictionary of fields to highlight in child docs.
    :param hl_tag: The HTML tag to use for highlighting matched fragments.
    :param highlighting: Whether highlighting should be enabled in docs.
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

        if not highlighting:
            # If highlighting is not enabled, return
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
    query: QueryString | str,
    order_by: tuple[str, str],
    default_score: int,
    default_current_date: datetime.date | None = None,
) -> QueryString:
    """Build a custom function score query for sorting based on a date field.

    Define the function score for sorting, based on the child sort_field. When
    the order is 'entry_date_filed desc', the 'date_filed_time' value, adjusted
    by sixteen_hundred_offset, is used as the score, sorting newer documents
    first. In 'asc' order, the score is the difference between 'current_time'
    (also adjusted by the sixteen_hundred_offset) and 'date_filed_time',
    prioritizing older documents. If a document does not have a 'date_filed'
    set, the function returns 1. This ensures that dockets containing documents
    without a 'date_filed' are displayed before dockets without filings, which
    have a default score of 0. sixteen_hundred_offset is based on 1600-01-01 because we
    have persons with dates of birth older than 1697. Ensuring all epoch
    millisecond values are positive and compatible with ES scoring system.
    This approach allows for handling dates in our system both before and
    after January 1, 1970 (epoch time), within a positive scoring range.

    :param query: The Elasticsearch query string or QueryString object.
    :param order_by: If provided the field to use to compute score for sorting
    results based on a child document field.
    :param default_score: The default score to return when the document lacks
    the sort field.
    :param default_current_date: The default current date to use for computing
     a stable date score across pagination in the V4 Search API.
    :return: The modified QueryString object with applied function score.
    """

    default_current_time = None
    if default_current_date:
        midnight_current_date = datetime.datetime.combine(
            default_current_date, datetime.time()
        )
        default_current_time = int(midnight_current_date.timestamp() * 1000)

    sort_field, order = order_by
    query = Q(
        "function_score",
        query=query,
        script_score={
            "script": {
                "source": f"""
                    long current_time;
                    if (params.default_current_time != null) {{
                            current_time = params.default_current_time;  // Use 'default_current_time' if provided
                        }} else {{
                           current_time = new Date().getTime();
                        }}
                    // Check if the document has a value for the 'sort_field'
                    if (doc['{sort_field}'].size() == 0) {{
                        return {default_score};  // If not, return 'default_score' as the score
                    }} else {{
                        // Offset based on the positive epoch time for 1600-01-01 to ensure positive scores.
                        long sixteen_hundred_offset = 11676096000000L;
                        // Get the current time in milliseconds, include the sixteen_hundred_offset to work with positive epoch times.
                        current_time = current_time + sixteen_hundred_offset;

                        // Convert the 'sort_field' value to epoch milliseconds, adjusting by the same offset.
                        long date_filed_time = doc['{sort_field}'].value.toInstant().toEpochMilli() + sixteen_hundred_offset;

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
                "params": {
                    "order": order,
                    "default_score": default_score,
                    "default_current_time": default_current_time,
                },
            },
        },
        # Replace the original score with the one computed by the script
        boost_mode="replace",
    )

    return query


def build_decay_relevance_score(
    query: QueryString | str,
    date_field: str,
    scale: int,
    decay: float,
    default_missing_date: str = "1600-01-01T00:00:00Z",
    boost_mode: str = "multiply",
    min_score: float = 0.0,
) -> QueryString:
    """
    Build a decay relevance score query for Elasticsearch that adjusts the
    relevance of documents based on a date field.

    :param query: The Elasticsearch query string or QueryString object.
    :param date_field: The date field used to compute the relevance decay.
    :param scale: The scale (in years) that determines the rate of decay.
    :param decay: The decay factor.
    :param default_missing_date: The default date to use when the date field
    is null.
    :param boost_mode: The mode to combine the decay score with the query's
    original relevance score.
    :param min_score: The minimum score where the decay function stabilizes.
    :return:  The modified QueryString object with applied function score.
    """

    query = Q(
        "function_score",
        query=query,
        script_score={
            "script": {
                "source": f"""
                    def default_missing_date = Instant.parse(params.default_missing_date).toEpochMilli();
                    def decay = (double)params.decay;
                    def now = new Date().getTime();
                    def min_score = (double)params.min_score;

                    // Convert scale parameter into milliseconds.
                    double years = (double)params.scale;
                    // Convert years to milliseconds 1 year = 365 days
                    long scaleMillis = (long)(years * 365 * 24 * 60 * 60 * 1000);

                    // Retrieve the document date. If missing or null, use default_missing_date
                    def docDate = default_missing_date;
                    if (doc['{date_field}'].size() > 0) {{
                        docDate = doc['{date_field}'].value.toInstant().toEpochMilli();
                    }}
                    // λ = ln(decay)/scale
                    def lambda = Math.log(decay) / scaleMillis;
                    // Absolute distance from now
                    def diff = Math.abs(docDate - now);
                    // Score: exp( λ * max(0, |docDate - now|) )
                    def decay_score = Math.exp(lambda * diff);
                    // Adjust the decay score to have a minimum value
                    return min_score + ((1 - min_score) * decay_score);
                    """,
                "params": {
                    "default_missing_date": default_missing_date,
                    "scale": scale,  # Years
                    "decay": decay,
                    "min_score": min_score,
                },
            },
        },
        boost_mode=boost_mode,
    )
    return query


def build_has_child_query(
    query: QueryString | str,
    child_type: str,
    child_hits_limit: int,
    highlighting_fields: dict[str, int] | None = None,
    order_by: tuple[str, str] | None = None,
    child_highlighting: bool = True,
    default_current_date: datetime.date | None = None,
    alerts: bool = False,
) -> QueryString:
    """Build a 'has_child' query.

    :param query: The Elasticsearch query string or QueryString object.
    :param child_type: The type of the child document.
    :param child_hits_limit: The maximum number of child hits to be returned.
    :param highlighting_fields: List of fields to highlight in child docs.
    :param order_by: If provided the field to use to compute score for sorting
    results based on a child document field.
    :param child_highlighting: Whether highlighting should be enabled in child docs.
    :param default_current_date: The default current date to use for computing
     a stable date score across pagination in the V4 Search API.
    :param alerts: If highlighting is being applied to search Alerts hits.
    :return: The 'has_child' query.
    """

    if (
        order_by
        and all(order_by)
        and child_type == "recap_document"
        and order_by[0] == "entry_date_filed"
    ):
        query = build_custom_function_score_for_date(
            query,
            order_by,
            default_score=1,
            default_current_date=default_current_date,
        )

    hl_tag = ALERTS_HL_TAG if alerts else SEARCH_HL_TAG
    highlight_options, fields_to_exclude = build_highlights_dict(
        highlighting_fields, hl_tag, child_highlighting
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


def combine_plain_filters_and_queries(
    cd: CleanData,
    filters: list,
    string_query: QueryString | list,
    api_version: Literal["v3", "v4"] | None = None,
) -> Query:
    """Combine filters and query strings for plain documents, like Oral arguments
    and Parentheticals.

    :param cd: The query CleanedData
    :param filters: A list of filter objects to be applied.
    :param string_query: An Elasticsearch QueryString object.
    :param api_version: Optional, the request API version.
    :return: The modified Search object based on the given conditions.
    """

    final_query = Q(string_query or "bool")
    if filters:
        final_query.filter = reduce(operator.iand, filters)
    if filters and string_query:
        final_query.minimum_should_match = 1
    return final_query


def get_match_all_query(
    cd: CleanData,
    api_version: Literal["v3", "v4"] | None = None,
    child_highlighting: bool = True,
) -> Query:
    """Build and return a match-all query for each type of document.

    :param cd: The query CleanedData
    :param api_version: Optional, the request API version.
    :param child_highlighting: Whether highlighting should be enabled in child docs.
    :return: The Match All Query object.
    """
    _, query_hits_limit = get_child_top_hits_limit(
        cd, cd["type"], api_version=api_version
    )
    hl_fields = api_child_highlight_map.get(
        (child_highlighting, cd["type"]), {}
    )
    match cd["type"]:
        case SEARCH_TYPES.PEOPLE:
            match_all_child_query = build_has_child_query(
                "match_all",
                "position",
                query_hits_limit,
                hl_fields,
                None,
                child_highlighting=child_highlighting,
            )
            q_should = [
                match_all_child_query,
                Q("match", person_child="person"),
            ]
            final_match_all_query = Q(
                "bool", should=q_should, minimum_should_match=1
            )
        case SEARCH_TYPES.RECAP | SEARCH_TYPES.DOCKETS:
            # Match all query for RECAP and Dockets, it'll return dockets
            # with child documents and also empty dockets.
            match_all_child_query = build_has_child_query(
                "match_all",
                "recap_document",
                query_hits_limit,
                hl_fields,
                get_function_score_sorting_key(cd, api_version),
                child_highlighting=child_highlighting,
                default_current_date=cd.get("request_date"),
            )
            match_all_parent_query = Q("match", docket_child="docket")
            match_all_parent_query = nullify_query_score(
                match_all_parent_query
            )
            final_match_all_query = Q(
                "bool",
                should=[match_all_child_query, match_all_parent_query],
                minimum_should_match=1,
            )
        case SEARCH_TYPES.OPINION:
            # Only return Opinion clusters.
            match_all_child_query = build_has_child_query(
                "match_all",
                "opinion",
                query_hits_limit,
                hl_fields,
                None,
                child_highlighting=child_highlighting,
            )
            q_should = [
                match_all_child_query,
                Q("match", cluster_child="opinion_cluster"),
            ]
            final_match_all_query = Q(
                "bool", should=q_should, minimum_should_match=1
            )
        case _:
            # No string_query or filters in plain search types like OA and
            # Parentheticals. Use a match_all query.
            final_match_all_query = Q("match_all")

    return final_match_all_query


def build_es_base_query(
    search_query: Search,
    cd: CleanData,
    child_highlighting: bool = True,
    api_version: Literal["v3", "v4"] | None = None,
    alerts: bool = False,
) -> EsMainQueries:
    """Builds filters and fulltext_query based on the given cleaned
     data and returns an elasticsearch query.

    :param search_query: The Elasticsearch search query object.
    :param cd: The cleaned data object containing the query and filters.
    :param child_highlighting: Whether highlighting should be enabled in child
    docs.
    :param api_version: Optional, the request API version.
    :param alerts: If highlighting is being applied to search Alerts hits.
    :return: An `EsMainQueries` object containing the Elasticsearch search
    query object and an ES QueryString for child documents or None if there is
    no need to query child documents and a QueryString for parent documents or
    None.
    """

    main_query = None
    string_query = None
    child_query = None
    parent_query = None
    filters = []
    plain_doc = False
    join_queries = None
    has_text_query = False
    match_all_query = False
    match cd["type"]:
        case SEARCH_TYPES.PARENTHETICAL:
            filters = build_es_plain_filters(cd)
            string_query = build_fulltext_query(
                ["representative_text"], cd.get("q", "")
            )
            plain_doc = True
        case SEARCH_TYPES.ORAL_ARGUMENT:
            filters = build_es_plain_filters(cd)
            fields = SEARCH_ORAL_ARGUMENT_QUERY_FIELDS.copy()
            fields.extend(add_fields_boosting(cd))
            string_query = build_fulltext_query(
                fields,
                cd.get("q", ""),
            )
            plain_doc = True
        case SEARCH_TYPES.PEOPLE:
            child_fields = SEARCH_PEOPLE_CHILD_QUERY_FIELDS.copy()
            child_fields.extend(
                add_fields_boosting(
                    cd,
                    [
                        "appointer",
                        "supervisor",
                        "predecessor",
                        # Person field.
                        "name",
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
            join_queries = build_full_join_es_queries(
                cd,
                child_query_fields,
                parent_query_fields,
                child_highlighting=child_highlighting,
                api_version=api_version,
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
                    list(recap_boosts_es.keys()),
                )
            )
            child_query_fields = {"recap_document": child_fields}
            parent_query_fields = SEARCH_RECAP_PARENT_QUERY_FIELDS.copy()
            parent_query_fields.extend(
                add_fields_boosting(
                    cd,
                    [
                        "docketNumber",
                        "caseName.exact",
                    ],
                )
            )
            join_queries = build_full_join_es_queries(
                cd,
                child_query_fields,
                parent_query_fields,
                child_highlighting=child_highlighting,
                api_version=api_version,
                alerts=alerts,
            )

        case SEARCH_TYPES.OPINION:
            str_query = cd.get("q", "")
            related_match = RELATED_PATTERN.search(str_query)
            mlt_query = None
            if related_match:
                cluster_pks = related_match.group("pks").split(",")
                mlt_query = async_to_sync(build_more_like_this_query)(
                    cluster_pks
                )
                join_queries = build_full_join_es_queries(
                    cd,
                    {"opinion": []},
                    [],
                    mlt_query,
                    child_highlighting=True,
                    api_version=api_version,
                )
                return EsMainQueries(
                    search_query=search_query.query(join_queries.main_query),
                    boost_mode="multiply",
                    parent_query=join_queries.parent_query,
                    child_query=join_queries.child_query,
                )

            opinion_search_fields = SEARCH_OPINION_QUERY_FIELDS
            child_fields = opinion_search_fields.copy()
            child_fields.extend(
                add_fields_boosting(
                    cd,
                    [
                        "type",
                        "text",
                        "caseName.exact",
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
                        "caseName.exact",
                        "docketNumber",
                    ],
                )
            )
            join_queries = build_full_join_es_queries(
                cd,
                child_query_fields,
                parent_query_fields,
                mlt_query,
                child_highlighting=child_highlighting,
                api_version=api_version,
                alerts=alerts,
            )

    if join_queries is not None:
        main_query = join_queries.main_query
        parent_query = join_queries.parent_query
        child_query = join_queries.child_query
        has_text_query = join_queries.has_text_query

    if not any([filters, string_query, main_query]):
        # No filters, string_query or main_query provided by the user, return a
        # match_all query
        main_query = get_match_all_query(cd, api_version, child_highlighting)
        match_all_query = True

    boost_mode = "multiply" if has_text_query else "replace"
    if plain_doc and not match_all_query:
        # Combine the filters and string query for plain documents like Oral
        # arguments and parentheticals
        main_query = combine_plain_filters_and_queries(
            cd, filters, string_query, api_version
        )
        boost_mode = "multiply" if string_query else "replace"

    # Apply a custom function score to the main query, useful for cursor pagination
    # in the V4 API and for date decay relevance.
    main_query = apply_custom_score_to_main_query(
        cd, main_query, api_version, boost_mode=boost_mode
    )

    return EsMainQueries(
        search_query=search_query.query(main_query),
        boost_mode=boost_mode,
        parent_query=parent_query,
        child_query=child_query,
    )


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
    child_docs_query: QueryString | None,
    cd: CleanData,
    exclude_docs_for_empty_field: str = "",
) -> QueryString:
    """Build a query for counting child documents in Elasticsearch, using the
    has_child query filters and queries. And append a match filter to only
    retrieve RECAPDocuments or OpinionDocuments. Utilized when it is required
    to retrieve child documents directly, such as in the Opinions Feed,
    RECAP Feed, RECAP Documents count query, and V4 RECAP_DOCUMENT Search API.

    :param child_docs_query: Existing Elasticsearch QueryString object or None
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

    if not child_docs_query:
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

    query_dict = child_docs_query.to_dict()
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
    es_queries = build_es_base_query(search_query, cd)
    search_query = es_queries.search_query
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
    es_queries = build_es_base_query(search_query, cd)
    search_query = es_queries.search_query
    child_docs_query = es_queries.child_query
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
            child_docs_count_query = build_child_docs_query(
                child_docs_query, cd
            )
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
    search_query: Search,
    cd: CleanData,
    alerts: bool = False,
    highlighting: bool = True,
) -> Search:
    """Add elasticsearch highlighting to the main search query.

    :param search_query: The Elasticsearch search query object.
    :param cd: The user input CleanedData
    :param alerts: If highlighting is being applied to search Alerts hits.
    :param highlighting: Whether highlighting should be enabled in docs.
    :return: The modified Elasticsearch search query object with highlights set
    """

    # Avoid highlighting for the related cluster query.
    related_match = RELATED_PATTERN.search(cd.get("q", ""))
    if related_match:
        return search_query

    highlighting_fields = {}
    highlighting_keyword_fields = []
    hl_tag = ALERTS_HL_TAG if alerts else SEARCH_HL_TAG
    match cd["type"]:
        case SEARCH_TYPES.ORAL_ARGUMENT:
            highlighting_fields = (
                SEARCH_ALERTS_ORAL_ARGUMENT_ES_HL_FIELDS
                if alerts
                else SEARCH_ORAL_ARGUMENT_ES_HL_FIELDS
            )
        case SEARCH_TYPES.PEOPLE:
            highlighting_fields = PEOPLE_ES_HL_FIELDS
            highlighting_keyword_fields = PEOPLE_ES_HL_KEYWORD_FIELDS
        case SEARCH_TYPES.RECAP | SEARCH_TYPES.DOCKETS:
            highlighting_fields = SEARCH_RECAP_HL_FIELDS
        case SEARCH_TYPES.OPINION:
            highlighting_fields = SEARCH_OPINION_HL_FIELDS

    # Use FVH in testing and documents that already support FVH.
    highlight_options, fields_to_exclude = build_highlights_dict(
        highlighting_fields, hl_tag, highlighting=highlighting
    )

    # Keyword fields do not support term_vector indexing; thus, FVH is not
    # supported either. Use plain text in this case. Keyword fields don't
    # have an exact version, so no HL merging is required either.
    if highlighting_keyword_fields and highlighting:
        for field in highlighting_keyword_fields:
            highlight_options["fields"][field] = {
                "type": "plain",
                "number_of_fragments": 0,
                "pre_tags": [f"<{hl_tag}>"],
                "post_tags": [f"</{hl_tag}>"],
            }

    extra_options = {"highlight": highlight_options}
    search_query = search_query.extra(**extra_options)
    search_query = search_query.source(excludes=fields_to_exclude)
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
                date_obj = datetime.date.fromisoformat(date_str)
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
    positions: QuerySet[Position, Position],
    request_type: Literal["frontend", "v3", "v4"] = "frontend",
) -> BasePositionMapping | ApiPositionMapping:
    """Extract all the data from the position queryset and
    fill the attributes of the mapping.

    :param positions: List of position records.
    :param request_type: The request type, frontend or api v3 or api v4.
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
                elif isinstance(
                    field_value, (datetime.datetime | datetime.date)
                ):
                    field_value = midnight_pt(field_value)

                mapping_dict[person_id].append(field_value)

    return position_db_mapping


def merge_unavailable_fields_on_parent_document(
    results: Page | dict | Response,
    search_type: str,
    request_type: Literal["frontend", "v3", "v4"] = "frontend",
    highlight: bool = True,
) -> None:
    """Merges unavailable fields on parent document from the database into
    search results, not all fields are required in frontend, so that fields are
    completed according to the received request_type (frontend or api).

    :param results: A Page object containing the search results to be modified.
    :param search_type: The search type to perform.
    :param request_type: The request type, frontend or api v3 or api v4.
    :param highlight: Whether highlighting is enabled.
    :return: None, the function modifies the search results object in place.
    """

    match search_type:
        case SEARCH_TYPES.PEOPLE if request_type != "v4":
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
        case SEARCH_TYPES.RECAP | SEARCH_TYPES.RECAP_DOCUMENT if (
            request_type == "v4" and not highlight
        ):
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
                        rd["_source"]["plain_text"] = recap_docs_dict.get(
                            rd["_source"]["id"], ""
                        )
                else:
                    result["plain_text"] = recap_docs_dict.get(
                        result["id"], ""
                    )

        case SEARCH_TYPES.RECAP | SEARCH_TYPES.DOCKETS if (
            request_type == "frontend"
        ):
            # Merge initial document button to the frontend search results.
            docket_ids = {doc["docket_id"] for doc in results}
            # This query retrieves initial documents considering two
            # possibilities:
            # 1. For district, bankruptcy, and appellate entries where we don't know
            #    if the entry contains attachments, it considers:
            #    document_number=1 and attachment_number=None and document_type=PACER_DOCUMENT
            #    This represents the main document with document_number 1.
            # 2. For appellate entries where the attachment page has already been
            #    merged, it considers:
            #    document_number=1 and attachment_number=1 and document_type=ATTACHMENT
            #    This represents document_number 1 that has been converted to an attachment.

            appellate_court_ids = (
                Court.federal_courts.appellate_pacer_courts().values_list(
                    "pk", flat=True
                )
            )
            initial_documents = (
                RECAPDocument.objects.filter(
                    QObject(
                        QObject(
                            attachment_number=None,
                            document_type=RECAPDocument.PACER_DOCUMENT,
                        )
                        | QObject(
                            attachment_number=1,
                            document_type=RECAPDocument.ATTACHMENT,
                            docket_entry__docket__court_id__in=appellate_court_ids,
                        )
                    ),
                    docket_entry__docket_id__in=docket_ids,
                    document_number="1",
                )
                .select_related(
                    "docket_entry",
                    "docket_entry__docket",
                    "docket_entry__docket__court",
                )
                .only(
                    "pk",
                    "document_type",
                    "document_number",
                    "attachment_number",
                    "pacer_doc_id",
                    "is_available",
                    "filepath_local",
                    "docket_entry__docket_id",
                    "docket_entry__docket__slug",
                    "docket_entry__docket__pacer_case_id",
                    "docket_entry__docket__court__jurisdiction",
                    "docket_entry__docket__court_id",
                )
            )

            initial_documents_in_page = {}
            for initial_document in initial_documents:
                if initial_document.has_valid_pdf:
                    # Initial Document available
                    initial_documents_in_page[
                        initial_document.docket_entry.docket_id
                    ] = (
                        initial_document.get_absolute_url(),
                        None,
                        "Initial Document",
                    )
                else:
                    # Initial Document not available. Buy button.
                    initial_documents_in_page[
                        initial_document.docket_entry.docket_id
                    ] = (
                        None,
                        initial_document.pacer_url,
                        "Buy Initial Document",
                    )

            for result in results:
                document_url, buy_document_url, text_button = (
                    initial_documents_in_page.get(
                        result.docket_id, (None, None, "")
                    )
                )
                result["initial_document_url"] = document_url
                result["buy_initial_document_url"] = buy_document_url
                result["initial_document_text"] = text_button

        case SEARCH_TYPES.OPINION if request_type == "v4" and not highlight:
            # Retrieves the Opinion plain_text from the DB to fill the snippet
            # when highlighting is disabled. Considering the same prioritization
            # as in the OpinionDocument indexing into ES.

            opinion_ids = {
                doc["_source"]["id"]
                for entry in results
                for doc in entry["child_docs"]
            }
            opinions = (
                Opinion.objects.filter(pk__in=opinion_ids)
                .annotate(
                    text_to_show=Case(
                        When(
                            ~QObject(html_columbia=""),
                            then=Substr(
                                "html_columbia", 1, settings.NO_MATCH_HL_SIZE
                            ),
                        ),
                        When(
                            ~QObject(html_lawbox=""),
                            then=Substr(
                                "html_lawbox", 1, settings.NO_MATCH_HL_SIZE
                            ),
                        ),
                        When(
                            ~QObject(xml_harvard=""),
                            then=Substr(
                                "xml_harvard", 1, settings.NO_MATCH_HL_SIZE
                            ),
                        ),
                        When(
                            ~QObject(html_anon_2020=""),
                            then=Substr(
                                "html_anon_2020", 1, settings.NO_MATCH_HL_SIZE
                            ),
                        ),
                        When(
                            ~QObject(html=""),
                            then=Substr("html", 1, settings.NO_MATCH_HL_SIZE),
                        ),
                        default=Substr(
                            "plain_text", 1, settings.NO_MATCH_HL_SIZE
                        ),
                        output_field=TextField(),
                    )
                )
                .values("id", "text_to_show")
            )
            opinion_docs_dict = {
                doc["id"]: doc["text_to_show"] for doc in opinions
            }
            for result in results:
                for op in result["child_docs"]:
                    op["_source"]["text"] = html_decode(
                        strip_tags(
                            opinion_docs_dict.get(op["_source"]["id"], "")
                        )
                    )
        case SEARCH_TYPES.ORAL_ARGUMENT if (
            request_type == "v4" and not highlight
        ):
            # Retrieves the Audio transcript from the DB to fill the snippet
            # when highlighting is disabled.

            oa_ids = {entry["id"] for entry in results}
            oa_docs = Audio.objects.filter(pk__in=oa_ids).only(
                "id", "stt_transcript", "stt_status"
            )
            oa_docs_dict = {
                doc.id: (
                    trunc(
                        doc.transcript,
                        length=settings.NO_MATCH_HL_SIZE,
                    )
                    if doc.stt_status
                    else ""
                )
                for doc in oa_docs
            }
            for result in results:
                result["text"] = oa_docs_dict.get(result["id"], "")

        case _:
            return


def clean_count_query(search_query: Search) -> SearchDSL:
    """Cleans a given ES Search object for a count query.

    Modifies the input Search object by removing 'function_score' from the main
    query if present and/or 'inner_hits' from any 'has_child' queries within
    the 'should' clause of the boolean query.
    It then creates a new Search object with the modified query.

    :param search_query: The ES Search object.
    :return: A new ES Search object with the count query.
    """

    parent_total_query_dict = search_query.to_dict(count=True)
    try:
        # Clean function_score in queries that contain it
        parent_total_query_dict = parent_total_query_dict["query"][
            "function_score"
        ]
        del parent_total_query_dict["boost_mode"]
        del parent_total_query_dict["functions"]
    except KeyError:
        # Omit queries that don't contain it.
        pass

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
        # Set track_total_hits False to avoid retrieving the hit count in the main query.
        main_query = search_query.extra(
            from_=es_from, size=rows_per_page, track_total_hits=False
        )
        main_doc_count_query = clean_count_query(search_query)

        search_type = get_params.get("type", SEARCH_TYPES.OPINION)
        parent_unique_field = cardinality_query_unique_ids[search_type]
        main_doc_count_query = build_cardinality_count(
            main_doc_count_query, parent_unique_field
        )
        if child_docs_count_query:
            child_unique_field = cardinality_query_unique_ids[
                SEARCH_TYPES.RECAP_DOCUMENT
            ]
            child_total_query = build_cardinality_count(
                child_docs_count_query, child_unique_field
            )

        # Execute the ES main query + count queries in a single request.
        multi_search = MultiSearch()
        multi_search = multi_search.add(main_query).add(main_doc_count_query)
        if child_total_query:
            multi_search = multi_search.add(child_total_query)
        responses = multi_search.execute()

        main_response = responses[0]
        main_doc_count_response = responses[1]
        parent_total = simplify_estimated_count(
            main_doc_count_response.aggregations.unique_documents.value
        )
        if child_total_query:
            child_doc_count_response = responses[2]
            child_total = simplify_estimated_count(
                child_doc_count_response.aggregations.unique_documents.value
            )

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


def build_has_child_filters(cd: CleanData) -> list[QueryString | Range]:
    """Builds Elasticsearch 'has_child' filters based on the given child type
    and CleanData.

    :param cd: The user input CleanedData.
    :return: A list of QueryString objects containing the 'has_child' filters.
    """

    queries_list = []
    if cd["type"] == SEARCH_TYPES.PEOPLE:
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
        available_only = cd.get("available_only", "")
        description = cd.get("description", "")
        document_number = cd.get("document_number", "")
        attachment_number = cd.get("attachment_number", "")
        entry_date_filed_after = cd.get("entry_date_filed_after", "")
        entry_date_filed_before = cd.get("entry_date_filed_before", "")

        if available_only:
            queries_list.extend(
                build_term_query(
                    "is_available",
                    available_only,
                )
            )
        if description:
            queries_list.extend(build_text_filter("description", description))
        if document_number:
            queries_list.extend(
                build_term_query("document_number", document_number)
            )
        if attachment_number:
            queries_list.extend(
                build_term_query("attachment_number", attachment_number)
            )
        if entry_date_filed_after or entry_date_filed_before:
            queries_list.extend(
                build_daterange_query(
                    "entry_date_filed",
                    entry_date_filed_before,
                    entry_date_filed_after,
                )
            )

    return queries_list


def build_join_es_filters(cd: CleanData) -> list:
    """Builds parent join elasticsearch filters based on the CleanData object.

    :param cd: An object containing cleaned user data.
    :return: The list of Elasticsearch queries built.
    """

    queries_list = []
    if cd["type"] == SEARCH_TYPES.PEOPLE:
        # Build parent document filters.
        queries_list.extend(
            [
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
                *build_text_filter("caseName.exact", cd.get("case_name", "")),
                *build_term_query(
                    "docketNumber.exact",
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
                *build_text_filter("caseName.exact", cd.get("case_name", "")),
                *build_daterange_query(
                    "dateFiled",
                    cd.get("filed_before", ""),
                    cd.get("filed_after", ""),
                ),
                *build_term_query(
                    "docketNumber.exact",
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
    es_queries = build_es_base_query(search_query, cd)
    s = es_queries.search_query
    child_docs_query = es_queries.child_query
    if jurisdiction or cd["type"] == SEARCH_TYPES.RECAP:
        # An Opinion Jurisdiction feed or RECAP Search displays child documents
        # Eliminate items that lack the ordering field and apply highlighting
        # to create a snippet for the plain_text or text fields.
        s = build_child_docs_query(
            child_docs_query,
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


def apply_custom_score_to_main_query(
    cd: CleanData,
    query: Query,
    api_version: Literal["v3", "v4"] | None = None,
    boost_mode: str = "multiply",
) -> Query:
    """Apply a custom function score to the main query.

    :param cd: The query CleanedData
    :param query: The ES Query object to be modified.
    :param api_version: Optional, the request API version.
    :param boost_mode: Optional, the boost mode to apply for the decay relevancy score
    :return: The function_score query contains the base query, applied when
    child_order is used.
    """
    child_order_by = get_function_score_sorting_key(cd, api_version)
    valid_child_order_by = bool(child_order_by and all(child_order_by))
    valid_custom_score_fields = {
        SEARCH_TYPES.RECAP: ["dateFiled"],
        SEARCH_TYPES.DOCKETS: ["dateFiled"],
        SEARCH_TYPES.RECAP_DOCUMENT: ["dateFiled", "entry_date_filed"],
        SEARCH_TYPES.PEOPLE: ["dob", "dod"],
        SEARCH_TYPES.ORAL_ARGUMENT: ["dateArgued"],
    }

    sort_field, order = child_order_by if valid_child_order_by else ("", None)
    is_valid_custom_score_field = (
        sort_field in valid_custom_score_fields.get(cd["type"], [])
        if sort_field
        else False
    )

    valid_decay_relevance_types: dict[str, dict[str, str | int | float]] = (
        date_decay_relevance_types
    )
    main_order_by = cd.get("order_by", "")
    if is_valid_custom_score_field and api_version == "v4":
        # Applies a custom function score to sort Documents based on
        # a date field. This serves as a workaround to enable the use of the
        # search_after cursor for pagination on documents with a None dates.
        query = build_custom_function_score_for_date(
            query,
            child_order_by,
            default_score=0,
            default_current_date=cd["request_date"],
        )
    elif (
        main_order_by == "score desc"
        and cd["type"] in valid_decay_relevance_types
    ):
        decay_settings = valid_decay_relevance_types[cd["type"]]
        date_field = str(decay_settings["field"])
        scale = int(decay_settings["scale"])
        decay = float(decay_settings["decay"])
        min_score = float(decay_settings["min_score"])
        query = build_decay_relevance_score(
            query,
            date_field,
            scale=scale,
            decay=decay,
            boost_mode=boost_mode,
            min_score=min_score,
        )
    return query


def build_full_join_es_queries(
    cd: CleanData,
    child_query_fields: dict[str, list[str]],
    parent_query_fields: list[str],
    mlt_query: Query | None = None,
    child_highlighting: bool = True,
    api_version: Literal["v3", "v4"] | None = None,
    alerts: bool = False,
) -> EsJoinQueries:
    """Build a complete Elasticsearch query with both parent and child document
      conditions.

    :param cd: The query CleanedData
    :param child_query_fields: A dictionary mapping child fields document type.
    :param parent_query_fields: A list of fields for the parent document.
    :param mlt_query: the More Like This Query object.
    :param child_highlighting: Whether highlighting should be enabled in child docs.
    :param api_version: Optional, the request API version.
    :param alerts: If highlighting is being applied to search Alerts hits.
    :return: A three-tuple: the main join query, the child documents query, and
    the parent documents query.
    """

    q_should = []
    has_text_query = False
    match cd["type"]:
        case (
            SEARCH_TYPES.RECAP
            | SEARCH_TYPES.DOCKETS
            | SEARCH_TYPES.RECAP_DOCUMENT
        ):
            child_type = "recap_document"
        case SEARCH_TYPES.OPINION:
            child_type = "opinion"
        case SEARCH_TYPES.PEOPLE:
            child_type = "position"

    child_docs_query = None
    parent_query = None
    if cd["type"] in [
        SEARCH_TYPES.RECAP,
        SEARCH_TYPES.DOCKETS,
        SEARCH_TYPES.RECAP_DOCUMENT,
        SEARCH_TYPES.OPINION,
        SEARCH_TYPES.PEOPLE,
    ]:
        # Build child filters.
        child_filters = build_has_child_filters(cd)
        # Copy the original child_filters before appending parent fields.
        # For its use later in the parent filters.
        child_filters_original = deepcopy(child_filters)
        # Build child text query.
        child_fields = child_query_fields[child_type]

        if mlt_query:
            child_text_query = [mlt_query]
        else:
            child_text_query = build_fulltext_query(
                child_fields, cd.get("q", ""), only_queries=True
            )

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
                    or query.fields[0] not in ["party", "attorney", "firm"]
                ]
            )
            if parties_filters:
                # If party filters were provided, append a has_parent query
                # with the party filters included to match only child documents
                # whose parents match the party filters.
                child_filters.append(has_parent_parties_filter)

        # Build the child query based on child_filters and child child_text_query
        match child_filters, child_text_query:
            case [[], []]:
                pass
            case [[], _]:
                child_docs_query = Q(
                    "bool",
                    should=child_text_query,
                    minimum_should_match=1,
                )
            case [_, []]:
                child_docs_query = Q(
                    "bool",
                    filter=child_filters,
                )
            case [_, _]:
                child_docs_query = Q(
                    "bool",
                    filter=child_filters,
                    should=child_text_query,
                    minimum_should_match=1,
                )

        _, query_hits_limit = get_child_top_hits_limit(
            cd, cd["type"], api_version=api_version
        )
        has_child_query = None
        if child_text_query or child_filters:
            hl_fields = api_child_highlight_map.get(
                (child_highlighting, cd["type"]), {}
            )
            has_child_query = build_has_child_query(
                child_docs_query,
                child_type,
                query_hits_limit,
                hl_fields,
                get_function_score_sorting_key(cd, api_version),
                child_highlighting=child_highlighting,
                default_current_date=cd.get("request_date"),
                alerts=alerts,
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
                get_function_score_sorting_key(cd, api_version),
                default_current_date=cd.get("request_date"),
                alerts=alerts,
            )

        if has_child_query:
            q_should.append(has_child_query)

        # Build the parent filter and text queries.
        string_query = build_fulltext_query(
            parent_query_fields, cd.get("q", ""), only_queries=True
        )
        has_text_query = True if string_query else False

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
        parent_filter_dict = {
            "opinion": Q("match", cluster_child="opinion_cluster"),
            "recap_document": Q("match", docket_child="docket"),
            "position": Q("match", person_child="person"),
        }
        default_parent_filter = parent_filter_dict[child_type]
        match parent_filters, string_query:
            case [[], []]:
                pass
            case [[], _]:
                parent_query = Q(
                    "bool",
                    filter=default_parent_filter,
                    should=string_query,
                    minimum_should_match=1,
                )
            case [_, []]:
                parent_filters.extend([default_parent_filter])
                parent_query = Q(
                    "bool",
                    filter=parent_filters,
                )
            case [_, _]:
                parent_filters.extend([default_parent_filter])
                parent_query = Q(
                    "bool",
                    filter=parent_filters,
                    should=string_query,
                    minimum_should_match=1,
                )
        if parent_query and not mlt_query:
            q_should.append(parent_query)

    if not q_should:
        return EsJoinQueries(
            main_query=[],
            parent_query=parent_query,
            child_query=child_docs_query,
            has_text_query=has_text_query,
        )

    return EsJoinQueries(
        main_query=Q(
            "bool",
            should=q_should,
        ),
        parent_query=parent_query,
        child_query=child_docs_query,
        has_text_query=has_text_query,
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
        case SEARCH_TYPES.RECAP | SEARCH_TYPES.DOCKETS:
            child_type = "recap_document"
        case SEARCH_TYPES.PEOPLE:
            child_type = "position"
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
    search_params: QueryDict | CleanData,
    search_type: str,
    api_version: Literal["v3", "v4"] | None = None,
) -> tuple[int, int]:
    """Get the frontend and query hit limits for child documents.

    :param search_params: Either a QueryDict or CleanData object containing the
    search parameters.
    :param search_type: Elasticsearch DSL Search object
    :param api_version: Optional, the request API version.
    :return: A two-tuple containing the limit for child hits to display and the
    limit for child query hits
    """

    docket_id_query = re.search(r"docket_id:\d+", search_params.get("q", ""))
    if docket_id_query and search_type in [
        SEARCH_TYPES.RECAP,
        SEARCH_TYPES.DOCKETS,
    ]:
        return settings.VIEW_MORE_CHILD_HITS, settings.VIEW_MORE_CHILD_HITS + 1

    match search_type:
        case SEARCH_TYPES.RECAP:
            child_limit = settings.RECAP_CHILD_HITS_PER_RESULT
        case SEARCH_TYPES.DOCKETS:
            # For the DOCKETS type, show only one RECAP document per docket
            child_limit = 1
        case SEARCH_TYPES.OPINION:
            child_limit = settings.OPINION_HITS_PER_RESULT
        case SEARCH_TYPES.PEOPLE:
            child_limit = settings.PEOPLE_HITS_PER_RESULT
        case _:
            return 0, 1

    # Increase the RECAP_CHILD_HITS_PER_RESULT value by 1. This is done to determine
    # whether there are more than RECAP_CHILD_HITS_PER_RESULT results, which would
    # trigger the "View Additional Results" button on the frontend.
    query_hits_limit = (
        0
        if (search_type == SEARCH_TYPES.PEOPLE and not api_version == "v4")
        else child_limit + 1
    )
    return child_limit, query_hits_limit


def do_count_query(
    search_query: Search,
) -> int:
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
        # Required for the paginator class to work, as it expects an integer.
        total_results = 0
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

    alerts = True if hl_tag == ALERTS_HL_TAG else False
    try:
        es_queries = build_es_base_query(
            search_query, cd, cd["highlight"], api_version, alerts=alerts
        )
        s = es_queries.search_query
        child_docs_query = es_queries.child_query
    except (
        UnbalancedParenthesesQuery,
        UnbalancedQuotesQuery,
        BadProximityQuery,
        DisallowedWildcardPattern,
    ) as e:
        raise ElasticBadRequestError(detail=e.message)

    extra_options: dict[str, dict[str, Any]] = {}
    if api_version == "v3":
        # Build query parameters for the ES V3 Search API endpoints.
        # V3 endpoints display child documents. Here, the child documents query
        # is retrieved, and extra parameters like highlighting, field exclusion,
        # and sorting are set.
        # Note that in V3 Case Law Search, opinions are collapsed by cluster_id
        # meaning that only one result per cluster is shown.
        child_docs_query = build_child_docs_query(
            child_docs_query,
            cd=cd,
        )
        main_query = apply_custom_score_to_main_query(
            cd, child_docs_query, api_version, boost_mode=es_queries.boost_mode
        )
        main_query = search_query.query(main_query)
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
        elif cd["type"] == SEARCH_TYPES.DOCKETS:
            extra_options.update(
                {
                    "collapse": {
                        "field": "docket_id",
                    }
                }
            )

        main_query = main_query.extra(**extra_options)
        if cd["type"] == SEARCH_TYPES.RECAP:
            # In the RECAP type, the dateFiled sorting param is converted to
            # entry_date_filed
            cd["order_by"] = map_to_docket_entry_sorting(cd["order_by"])
        main_query = main_query.sort(
            build_sort_results(cd, api_version=api_version)
        )
    else:
        child_docs_query = build_child_docs_query(
            child_docs_query,
            cd=cd,
        )
        # Build query params for the ES V4 Search API endpoints.
        if cd["type"] == SEARCH_TYPES.RECAP_DOCUMENT:
            # The RECAP_DOCUMENT search type returns only child documents.
            # Here, the child documents query is retrieved, highlighting and
            # field exclusion are set.

            s = apply_custom_score_to_main_query(
                cd,
                child_docs_query,
                api_version,
                boost_mode=es_queries.boost_mode,
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
            # DOCKETS, RECAP, OPINION, PEOPLE and ORAL_ARGUMENT search types. Use the same query
            # parameters as in the frontend. Only switch highlighting according
            # to the user request.
            main_query = add_es_highlighting(
                s, cd, alerts=alerts, highlighting=cd["highlight"]
            )

    return main_query, child_docs_query


def build_cardinality_count(count_query: Search, unique_field: str) -> Search:
    """Build an Elasticsearch cardinality aggregation.
    This aggregation estimates the count of unique documents based on the
    specified unique field. The precision_threshold, set by
    ELASTICSEARCH_CARDINALITY_PRECISION, determines the point at which the
    count begins to trade accuracy for performance. The error in the
    approximation count using this method ranges from 1% to 6%.
    https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations-metrics-cardinality-aggregation.html#_counts_are_approximate

    :param count_query: The Elasticsearch DSL Search object containing the
    count query.
    :param unique_field: The field name on which the cardinality aggregation
    will be based to estimate uniqueness.

    :return: The ES cardinality aggregation query.
    """

    count_query.aggs.bucket(
        "unique_documents",
        "cardinality",
        field=unique_field,
        precision_threshold=settings.ELASTICSEARCH_CARDINALITY_PRECISION,
    )
    return count_query.extra(size=0, track_total_hits=False)


def do_collapse_count_query(
    search_type: str, main_query: Search, query: Query
) -> int:
    """Execute an Elasticsearch count query for queries that uses collapse.
    Uses a query with aggregation to determine the number of unique opinions
    based on the 'cluster_id' or 'docket_id' according to the search_type.

    :param search_type: The search type to perform.
    :param main_query: The Elasticsearch DSL Search object.
    :param query: The ES Query object to perform the count query.
    :return: The results count.
    """

    unique_field = (
        "cluster_id" if search_type == SEARCH_TYPES.OPINION else "docket_id"
    )
    count_query = main_query.query(query)
    search_query = build_cardinality_count(count_query, unique_field)
    try:
        total_results = (
            search_query.execute().aggregations.unique_documents.value
        )
    except (TransportError, ConnectionError, RequestError) as e:
        logger.warning(
            f"Error on count query request: {search_query.to_dict()}"
        )
        logger.warning(f"Error was: {e}")
        total_results = 0
    return total_results


def do_es_alert_estimation_query(
    search_query: Search, cd: CleanData, day_count: int
) -> int:
    """Builds an ES alert estimation query based on the provided search query,
     clean data, and day count.

    :param search_query: The Elasticsearch search query object.
    :param cd: The cleaned data object containing the query and filters.
    :param day_count: The number of days to subtract from today's date to set
    the date range filter.
    :return: An integer representing the alert estimation.
    """

    match cd["type"]:
        case SEARCH_TYPES.OPINION | SEARCH_TYPES.RECAP:
            after_field = "filed_after"
            before_field = "filed_before"
        case SEARCH_TYPES.ORAL_ARGUMENT:
            after_field = "argued_after"
            before_field = "argued_before"
        case _:
            raise NotImplementedError

    cd[after_field] = datetime.date.today() - datetime.timedelta(
        days=int(day_count)
    )
    cd[before_field] = None
    es_queries = build_es_base_query(search_query, cd)
    estimation_query = es_queries.search_query
    if cd["type"] == SEARCH_TYPES.RECAP:
        # The RECAP estimation query consists of two requests: one to estimate
        # Docket hits and one to estimate RECAPDocument hits.
        del cd[after_field]
        del cd[before_field]
        cd["entry_date_filed_after"] = (
            datetime.date.today() - datetime.timedelta(days=int(day_count))
        )
        cd["entry_date_filed_before"] = None

        main_doc_count_query = clean_count_query(estimation_query)
        main_doc_count_query = main_doc_count_query.extra(
            size=0, track_total_hits=True
        )

        # Perform the two queries in a single request.
        multi_search = MultiSearch()
        multi_search = multi_search.add(main_doc_count_query)

        # Build RECAPDocuments count query.
        es_queries = build_es_base_query(search_query, cd)
        child_docs_query = es_queries.child_query
        child_docs_count_query = build_child_docs_query(child_docs_query, cd)
        child_total = 0
        if child_docs_count_query:
            child_docs_count_query = search_query.query(child_docs_count_query)
            child_total_query = child_docs_count_query.extra(
                size=0, track_total_hits=True
            )
            multi_search = multi_search.add(child_total_query)

        responses = multi_search.execute()
        parent_total = responses[0].hits.total.value
        if child_docs_count_query:
            child_doc_count_response = responses[1]
            child_total = child_doc_count_response.hits.total.value
        total_recap_estimation = parent_total + child_total
        return total_recap_estimation

    return estimation_query.count()


def do_es_sweep_alert_query(
    search_query: Search,
    child_search_query: Search,
    cd: CleanData,
) -> tuple[list[Hit] | None, Response | None, Response | None]:
    """Build an ES query for its use in the daily RECAP sweep index.

    :param search_query: Elasticsearch DSL Search object.
    :param child_search_query: The Elasticsearch DSL search query to perform
    the child-only query.
    :param cd: The query CleanedData
    :return: A two-tuple, the Elasticsearch search query object and an ES
    Query for child documents, or None if there is no need to query
    child documents.
    """

    search_form = SearchForm(cd)
    if search_form.is_valid():
        cd = search_form.cleaned_data
    else:
        return None, None, None
    es_queries = build_es_base_query(search_query, cd, True, alerts=True)
    s = es_queries.search_query
    parent_query = es_queries.parent_query
    child_query = es_queries.child_query
    main_query = add_es_highlighting(s, cd, alerts=True)
    main_query = main_query.sort(build_sort_results(cd))
    main_query = main_query.extra(
        from_=0, size=settings.SCHEDULED_ALERT_HITS_LIMIT
    )

    multi_search = MultiSearch()
    multi_search = multi_search.add(main_query)
    if parent_query:
        parent_search = search_query.query(parent_query)
        # Ensure accurate tracking of total hit count for up to 10,001 query results
        parent_search = parent_search.extra(
            from_=0,
            track_total_hits=settings.ELASTICSEARCH_MAX_RESULT_COUNT + 1,
        )
        parent_search = parent_search.source(includes=["docket_id"])
        multi_search = multi_search.add(parent_search)

    query_with_parties = cd.get("party_name") or cd.get("atty_name")
    # Avoid performing a child query on the ESRECAPSweepDocument index if the query
    # contains party-related fields, as they're not compatible with this index.
    # This query doesn't need to filter out child hits, since a RECAPDocument matched
    # by a query containing party fields is inherently a cross-object alert.
    if child_query and not query_with_parties:
        child_search = child_search_query.query(child_query)
        # Ensure accurate tracking of total hit count for up to 10,001 query results
        child_search = child_search.extra(
            from_=0,
            track_total_hits=settings.ELASTICSEARCH_MAX_RESULT_COUNT + 1,
        )
        child_search = child_search.source(includes=["id"])
        multi_search = multi_search.add(child_search)

    responses = multi_search.execute()
    main_results = responses[0]
    rd_results = None
    docket_results = None
    if parent_query:
        docket_results = responses[1]
    if child_query and not query_with_parties:
        rd_results = responses[2]

    # Re-run parent query to fetch potentially missed docket IDs due to large
    # result sets.
    should_repeat_parent_query = (
        docket_results
        and docket_results.hits.total.value
        >= settings.ELASTICSEARCH_MAX_RESULT_COUNT
    )
    if should_repeat_parent_query and parent_query:
        docket_ids = [int(d.docket_id) for d in main_results]
        # Adds extra filter to refine results.
        parent_query.filter.append(Q("terms", docket_id=docket_ids))
        parent_search = search_query.query(parent_query)
        parent_search = parent_search.source(includes=["docket_id"])
        docket_results = parent_search.execute()

    limit_inner_hits({}, main_results, cd["type"])
    set_results_highlights(main_results, cd["type"])

    # This block addresses a potential issue where the initial child query
    # might not return all expected results, especially when the result set is
    # large. To ensure complete data retrieval, it extracts child document IDs
    # from the main results and refines the child query filter with these IDs.
    # Finally, it re-executes the child search.
    should_repeat_child_query = (
        rd_results
        and rd_results.hits.total.value
        >= settings.ELASTICSEARCH_MAX_RESULT_COUNT
    )
    if should_repeat_child_query and child_query and not query_with_parties:
        rd_ids = [
            int(rd["_source"]["id"])
            for docket in main_results
            if hasattr(docket, "child_docs")
            for rd in docket.child_docs
        ]
        child_query.filter.append(Q("terms", id=rd_ids))
        child_search = child_search_query.query(child_query)
        child_search = child_search.source(includes=["id"])
        rd_results = child_search.execute()

    return main_results, docket_results, rd_results


def compute_lowest_possible_estimate(precision_threshold: int) -> int:
    """Estimates can be below reality by as much as 6%. Round numbers below that threshold.
    :return: The lowest possible estimate.
    """
    return int(precision_threshold * 0.94)


def simplify_estimated_count(search_count: int) -> int:
    """Simplify the estimated search count to the nearest rounded figure.
    It only applies this rounding if the search_count exceeds the
    ELASTICSEARCH_CARDINALITY_PRECISION threshold.

    :param search_count: The original search count.
    :return: The simplified search_count, rounded to the nearest significant
    figure or the original search_count if below the threshold.
    """

    if search_count >= compute_lowest_possible_estimate(
        settings.ELASTICSEARCH_CARDINALITY_PRECISION
    ):
        search_count_str = str(search_count)
        first_two = search_count_str[:2]
        zeroes = (len(search_count_str) - 2) * "0"
        return int(first_two + zeroes)
    return search_count


def set_child_docs_and_score(
    results: list[Hit] | list[dict[str, Any]] | Response,
    merge_highlights: bool = False,
    merge_score: bool = False,
) -> None:
    """Process and attach child documents to the main search results.

    :param results: A list of search results, which can be ES Hit objects
    or a list of dicts.
    :param merge_highlights: A boolean indicating whether to merge
    highlight data into the results.
    :param merge_score: A boolean indicating whether to merge
    the BM25 score into the results.
    :return: None. Results are modified in place.
    """

    for result in results:
        result_is_dict = isinstance(result, dict)
        if result_is_dict:
            # If the result is a dictionary, do nothing, or assign [] to
            # child_docs if it is not present.
            result["child_docs"] = result.get("child_docs", [])
        else:
            # Process child hits if the result is an ES AttrDict instance,
            # so they can be properly serialized.
            child_docs = getattr(result, "child_docs", [])
            result["child_docs"] = [
                defaultdict(lambda: None, doc["_source"].to_dict())
                for doc in child_docs
            ]

        # Optionally merges highlights. Used for integrating percolator
        # highlights into the percolated document.
        if merge_highlights and result_is_dict:
            meta_hl = result.get("meta", {}).get("highlight", {})
            merge_highlights_into_result(meta_hl, result)

        # Optionally merges the BM25 score for display in the API.
        if merge_score and isinstance(result, AttrDict):
            result["bm25_score"] = result.meta.score


def get_court_opinions_counts(
    search_query: Search, courts_count: int
) -> dict[str, int] | None:
    """Retrieve the opinion counts per each court.

    :param search_query: The ES DSL Search object.
    :param courts_count: The number of courts in the database, used as the size
    for the terms aggregation.
    :return: A dict mapping court IDs to their respective counts of
    opinions, or None if an error occurs during query execution.
    """

    search_query = search_query.extra(size=0)
    search_query = search_query.query(
        Q("bool", must=Q("match", cluster_child="opinion"))
    )
    search_query.aggs.bucket(
        "court_id", A("terms", field="court_id.raw", size=courts_count)
    )
    try:
        response = search_query.execute()
    except (TransportError, ConnectionError, RequestError):
        return None

    buckets = response.aggregations.court_id.buckets
    return {group["key"]: group["doc_count"] for group in buckets}


def get_opinions_coverage_over_time(
    search_query: Search, court_id: str, q: str | None, facet_field: str
) -> AttrList | None:
    """Retrieve the coverage of court opinions over time, grouped by year.

    :param search_query: The ES DSL Search object.
    :param court_id: The court ID or "all" to include opinions from all courts.
    :param q: Query string to filter the opinions.
    :param facet_field: The field used for the date aggregation.
    :return: An AttrList of buckets containing the yearly aggregation opinions
    or None if an error occurs during query execution.
    """

    search_query = search_query.extra(size=0)
    search_query = search_query.query("query_string", query=q or "*")
    search_query = search_query.filter("match", cluster_child="opinion")
    if court_id.lower() != "all":
        search_query = search_query.filter(
            "term", **{"court_id.exact": court_id}
        )
    search_query.aggs.bucket(
        "opinions_coverage_over_time",
        DateHistogram(
            field=facet_field,
            calendar_interval="year",
            min_doc_count=0,
            format="yyyy",
        ),
    )

    try:
        response = search_query.execute()
    except (TransportError, ConnectionError, RequestError):
        return None

    return response.aggregations.opinions_coverage_over_time.buckets


def get_opinions_coverage_chart_data(
    search_query: Search,
    court_ids: list[str],
) -> AttrList | list:
    """Fetches chart data for opinions coverage by filtering ES results
    and aggregating data by court IDs.

    :param search_query: The ES DSL Search object.
    :param court_ids: A list of court IDs used to filter the results.
    :return: An AttrList of buckets containing the aggregation of opinions by
    dateFiled or None if an error occurs during query execution.
    """

    search_query = search_query.filter("match", cluster_child="opinion")
    search_query = search_query.filter("terms", **{"court_id.raw": court_ids})
    court_agg = A("terms", field="court_id.raw", size=len(court_ids))
    date_stats = A("stats", field="dateFiled")

    search_query.aggs.bucket("courts", court_agg).metric(
        "date_range", date_stats
    )
    search_query = search_query.extra(size=0, track_total_hits=False)
    try:
        response = search_query.execute()
    except (TransportError, ConnectionError, RequestError):
        return []

    return response.aggregations.courts.buckets
