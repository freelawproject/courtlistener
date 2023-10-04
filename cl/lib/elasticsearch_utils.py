import logging
import operator
import re
import time
import traceback
from dataclasses import fields
from datetime import date, datetime
from functools import reduce, wraps
from typing import Any, Callable, Dict, List, Literal

from django.conf import settings
from django.core.paginator import Page
from django.db.models import QuerySet
from django.http.request import QueryDict
from django_elasticsearch_dsl.search import Search
from elasticsearch.exceptions import RequestError, TransportError
from elasticsearch_dsl import A, Q
from elasticsearch_dsl.connections import connections
from elasticsearch_dsl.query import QueryString, Range
from elasticsearch_dsl.response import Response
from elasticsearch_dsl.utils import AttrDict

from cl.lib.date_time import midnight_pt
from cl.lib.search_utils import (
    BOOSTS,
    cleanup_main_query,
    get_array_of_selected_fields,
)
from cl.lib.types import (
    ApiPositionMapping,
    BasePositionMapping,
    CleanData,
    ESRangeQueryParams,
)
from cl.people_db.models import Position
from cl.search.constants import (
    ALERTS_HL_TAG,
    BOOSTS,
    SEARCH_ALERTS_ORAL_ARGUMENT_ES_HL_FIELDS,
    SEARCH_HL_TAG,
    SEARCH_ORAL_ARGUMENT_ES_HL_FIELDS,
    SEARCH_ORAL_ARGUMENT_QUERY_FIELDS,
    SEARCH_PEOPLE_CHILD_QUERY_FIELDS,
    SEARCH_PEOPLE_PARENT_QUERY_FIELDS,
    SEARCH_RECAP_CHILD_HL_FIELDS,
    SEARCH_RECAP_CHILD_QUERY_FIELDS,
    SEARCH_RECAP_HL_FIELDS,
    SEARCH_RECAP_PARENT_QUERY_FIELDS,
    SOLR_OPINION_HL_FIELDS,
    SOLR_PEOPLE_ES_HL_FIELDS,
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


def es_index_exists(index_name: str) -> bool:
    """Confirm if the Elasticsearch index exists in the default instance.
    :param index_name: The index name to check.
    :return: True if the index exists, otherwise False.
    """
    try:
        es = connections.get_connection()
        index_exists = es.indices.exists(index=index_name)
    except (TransportError, ConnectionError) as e:
        logger.warning(
            f"Error in ES connection when checking index existence: {index_name}"
        )
        logger.warning(f"Error was: {e}")
        index_exists = False
    return index_exists


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
    ]:
        qf = BOOSTS["es"][cd["type"]].copy()

    if cd["type"] in [
        SEARCH_TYPES.ORAL_ARGUMENT,
        SEARCH_TYPES.RECAP,
        SEARCH_TYPES.DOCKETS,
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
        return [
            Q(
                "query_string",
                query=value,
                fields=[field],
                default_operator="AND",
            )
        ]
    return []


def build_sort_results(cd: CleanData) -> Dict:
    """Given cleaned data, find order_by value and return dict to use with
    ElasticSearch sort

    :param cd: The user input CleanedData
    :return: The short dict.
    """

    order_by_map = {
        "score desc": {"_score": {"order": "desc"}},
        "dateArgued desc": {"dateArgued": {"order": "desc"}},
        "dateArgued asc": {"dateArgued": {"order": "asc"}},
        "random_ desc": {"random_": {"order": "desc"}},
        "random_ asc": {"random_": {"order": "asc"}},
        "name_reverse asc": {"name_reverse": {"order": "asc"}},
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

    if cd["type"] == SEARCH_TYPES.PARENTHETICAL:
        order_by_map["score desc"] = {"score": {"order": "desc"}}

    if cd["type"] in [SEARCH_TYPES.RECAP, SEARCH_TYPES.DOCKETS]:
        random_order_field_id = "docket_id"
    else:
        random_order_field_id = "id"

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


def get_child_sorting_key(cd: CleanData) -> tuple[str, str]:
    """Given cleaned data, find order_by value and return a key to use within
    a has_child query.

    :param cd: The user input CleanedData
    :return: A two tuple containing the short key and the order (asc or desc).
    """
    order_by_map_child = {
        "entry_date_filed asc": ("entry_date_filed", "asc"),
        "entry_date_filed desc": ("entry_date_filed", "desc"),
    }
    order_by = cd.get("order_by", "")
    return order_by_map_child.get(order_by, ("", ""))


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


def build_has_child_query(
    query: QueryString | str,
    child_type: str,
    child_hits_limit: int,
    highlighting_fields: dict[str, int] | None = None,
    order_by: tuple[str, str] | None = None,
) -> QueryString:
    """Build a 'has_child' query.

    :param query: The Elasticsearch query string or QueryString object.
    :param child_type: The type of the child document.
    :param child_hits_limit: The maximum number of child hits to be returned.
    :param highlighting_fields: List of fields to highlight in child docs.
    :param order_by: If provided the field to use to compute score for sorting
    results based on a child document field.
    :return: The 'has_child' query.
    """

    if order_by and all(order_by):
        sort_field, order = order_by
        # Define the function score for sorting based in the child sort_field.
        query = Q(
            "function_score",
            query=query,
            script_score={
                "script": {
                    "source": f"""
                    // Check if the document has a value for the 'sort_field'
                    if (doc['{sort_field}'].size() == 0) {{
                        return 0;  // If not, return 0 as the score
                    }} else {{
                        // Get the current time in milliseconds
                        long current_time = new Date().getTime();

                        // Convert the 'sort_field' value to epoch milliseconds
                        long date_filed_time = doc['{sort_field}'].value.toInstant().toEpochMilli();

                        // If the order is 'desc', return the 'date_filed_time' as the score
                        if (params.order.equals('desc')) {{
                            return date_filed_time;
                        }} else {{
                            // Otherwise, calculate the difference between current time and 'date_filed_time'
                            // in order to boost older documents if the order is asc.
                            long diff = current_time - date_filed_time;

                            // Return the difference if it's non-negative, otherwise return 0
                            return diff >= 0 ? diff : 0;
                        }}
                    }}
                    """,
                    # Parameters passed to the script
                    "params": {"order": order},
                },
            },
            # Replace the original score with the one computed by the script
            boost_mode="replace",
        )

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
        highlight_options["fields"][field] = {
            "type": "plain",
            "fragment_size": fragment_size,
            "no_match_size": no_match_size,
            "number_of_fragments": number_of_fragments,
            "pre_tags": ["<mark>"],
            "post_tags": ["</mark>"],
            "max_analyzed_offset": 999_999,
        }

    inner_hits = {
        "name": f"filter_query_inner_{child_type}",
        "size": child_hits_limit,
        "_source": {
            "excludes": fields_to_exclude,
        },
    }
    if highlight_options:
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
) -> Search:
    """Get the appropriate search query based on the given parameters.

    :param cd: The query CleanedData
    :param search_query: Elasticsearch DSL Search object
    :param filters: A list of filter objects to be applied.
    :param string_query: An Elasticsearch QueryString object.
    :return: The modified Search object based on the given conditions.
    """
    if not any([filters, string_query]):
        match cd["type"]:
            case SEARCH_TYPES.PEOPLE:
                return search_query.query(Q("match", person_child="person"))
            case SEARCH_TYPES.RECAP | SEARCH_TYPES.DOCKETS:
                # Match all query for RECAP dn Dockets, it'll return dockets
                # with child documents and also empty dockets.
                _, query_hits_limit = get_child_top_hits_limit(cd, cd["type"])
                match_all_child_query = build_has_child_query(
                    "match_all",
                    "recap_document",
                    query_hits_limit,
                    SEARCH_RECAP_CHILD_HL_FIELDS,
                    get_child_sorting_key(cd),
                )
                match_all_parent_query = Q("match", docket_child="docket")
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
                            "name": f"text_query_inner_opinion",
                            "size": 10,
                        },
                    ),
                    Q("match_all"),
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
    search_query: Search, cd: CleanData
) -> tuple[Search, QueryString | None]:
    """Builds filters and fulltext_query based on the given cleaned
     data and returns an elasticsearch query.

    :param search_query: The Elasticsearch search query object.
    :param cd: The cleaned data object containing the query and filters.
    :return:The Elasticsearch search query object.
    """

    string_query = None
    join_query = None
    join_field_documents = [SEARCH_TYPES.PEOPLE, SEARCH_TYPES.OPINION]
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
            fields = SEARCH_ORAL_ARGUMENT_QUERY_FIELDS
            fields.extend(add_fields_boosting(cd))
            string_query = build_fulltext_query(
                fields,
                cd.get("q", ""),
            )
        case SEARCH_TYPES.PEOPLE:
            child_fields = SEARCH_PEOPLE_CHILD_QUERY_FIELDS
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
            parent_query_fields = SEARCH_PEOPLE_PARENT_QUERY_FIELDS
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
        case SEARCH_TYPES.RECAP | SEARCH_TYPES.DOCKETS:
            child_fields = SEARCH_RECAP_CHILD_QUERY_FIELDS
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
            parent_query_fields = SEARCH_RECAP_PARENT_QUERY_FIELDS
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
                cd, child_query_fields, parent_query_fields
            )
        case SEARCH_TYPES.OPINION:
            child_query_fields = {
                "opinion": add_fields_boosting(
                    cd,
                    [
                        "type",
                        "text",
                        # Cluster fields
                        "court",
                        "citation",
                        "judge",
                        "caseName",
                        "docketNumber",
                        "caseNameFull",
                        "caseNameShort",
                        "status",
                    ],
                ),
            }
            parent_query_fields = add_fields_boosting(
                cd,
                [
                    "court",
                    "citation",
                    "judge",
                    "caseName",
                    "docketNumber",
                    "caseNameFull",
                    "caseNameShort",
                    "status",
                ],
            )
            string_query = build_join_fulltext_queries(
                child_query_fields,
                parent_query_fields,
                cd.get("q", ""),
            )

    search_query = get_search_query(cd, search_query, filters, string_query)
    return search_query, join_query


def build_child_docs_query(
    join_query: QueryString | None, exclude_docs_for_empty_field: str = ""
) -> QueryString:
    """Build a query for counting child documents in Elasticsearch, using the
    has_child query filters and queries. And append a match filter to only
    retrieve RECAPDocuments.

    :param join_query: Existing Elasticsearch QueryString object or None
    :param exclude_docs_for_empty_field: Field that should not be empty for a
    document to be included
    :return: An Elasticsearch QueryString object
    """

    if not join_query:
        # Match all case.
        if not exclude_docs_for_empty_field:
            return Q("match", docket_child="recap_document")
        else:
            filters = [
                Q("match", docket_child="recap_document"),
                Q("exists", field=exclude_docs_for_empty_field),
            ]

            return Q("bool", filter=filters)

    query_dict = join_query.to_dict()
    if "filter" in query_dict["bool"]:
        existing_filter = query_dict["bool"]["filter"]
        existing_filter.append(Q("match", docket_child="recap_document"))
        if exclude_docs_for_empty_field:
            existing_filter.append(
                Q("exists", field=exclude_docs_for_empty_field)
            )

    else:
        query_dict["bool"]["filter"] = [
            Q("match", docket_child="recap_document")
        ]
        if exclude_docs_for_empty_field:
            query_dict["bool"]["filter"].append(
                Q("exists", field=exclude_docs_for_empty_field)
            )

    return Q(query_dict)


def build_es_main_query(
    search_query: Search, cd: CleanData
) -> tuple[Search, int | None, int, int | None]:
    """Builds and returns an elasticsearch query based on the given cleaned
     data, also performs grouping if required, add highlighting and returns
     additional query related metrics.

    :param search_query: The Elasticsearch search query object.
    :param cd: The cleaned data object containing the query and filters.
    :return: A three tuple, the Elasticsearch search query object after applying
    filters, string query and grouping if needed, the total number of results,
    the total number of top hits returned by a group if applicable.
    """
    search_query_base = search_query
    search_query, join_query = build_es_base_query(search_query, cd)
    total_query_results = do_count_query(search_query)
    top_hits_limit = 5
    total_child_results: int | None = None
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
                total_query_results,
                top_hits_limit,
                total_child_results,
            )
        case SEARCH_TYPES.RECAP | SEARCH_TYPES.DOCKETS:
            child_docs_count_query = build_child_docs_query(join_query)
            if child_docs_count_query:
                # Get the total RECAP Documents count.
                search_query_base = search_query_base.query(
                    child_docs_count_query
                )
                total_child_results = do_count_query(search_query_base)
        case _:
            pass

    search_query = add_es_highlighting(search_query, cd)
    search_query = search_query.sort(build_sort_results(cd))

    return (
        search_query,
        total_query_results,
        top_hits_limit,
        total_child_results,
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
            highlighting_fields = SOLR_PEOPLE_ES_HL_FIELDS
        case SEARCH_TYPES.RECAP | SEARCH_TYPES.DOCKETS:
            highlighting_fields = SEARCH_RECAP_HL_FIELDS
        case SEARCH_TYPES.OPINION:
            highlighting_fields = SOLR_OPINION_HL_FIELDS

    search_query = search_query.source(excludes=fields_to_exclude)
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
            marked_strings_exact = []
            # Extract all unique marked strings from "field.exact"
            marked_strings = re.findall(
                rf"<{tag}>.*?</{tag}>", highlight_list[0]
            )
            if field in highlights:
                # Extract all unique marked strings from "field" if
                # available
                marked_strings_exact = re.findall(
                    rf"<{tag}>.*?</{tag}>",
                    highlights[field][0],
                )

            # Merge highlights only if the exact.field contains highlight tags.
            # This avoids merging highlights when there are no matching terms,
            # yet highlights are returned due to the NO_MATCH_HL_SIZE setting.
            if marked_strings:
                unique_marked_strings = list(
                    set(marked_strings + marked_strings_exact)
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
            if hasattr(result.meta, "highlight"):
                highlights = result.meta.highlight.to_dict()
                merge_highlights_into_result(
                    highlights,
                    result,
                    SEARCH_HL_TAG,
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
                        SEARCH_HL_TAG,
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
    results: Page | dict,
    search_type: str,
    request_type: Literal["frontend", "api"] = "frontend",
) -> None:
    """Merges unavailable fields on parent document from the database into
    search results, not all fields are required in frontend, so that fields are
    completed according to the received request_type (frontend or api).

    :param results: A Page object containing the search results to be modified.
    :param search_type: The search type to perform.
    :param request_type: The request type, frontend or api.
    :return: None, the function modifies the search results object in place.
    """

    if search_type != SEARCH_TYPES.PEOPLE:
        return

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


def build_join_fulltext_queries(
    child_query_fields: dict[str, list[str]],
    parent_fields: list[str],
    value: str,
) -> QueryString | List:
    """Creates a full text query string for join parent-child documents.

    :param child_query_fields: A list of child name fields to search in.
    :param parent_fields: The parent fields to search in.
    :param value: The string value to search for.
    :return: A Elasticsearch QueryString or [] if the "value" param is empty.
    """

    if not value:
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

        query = Q(
            "has_child",
            type=child_type,
            score_mode="max",
            query=build_fulltext_query(fields, value),
            inner_hits=inner_hits,
        )
        q_should.append(query)

    # Build parent document fulltext queries.
    if parent_fields:
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
            court = cd.get("court", "").split()
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

    if cd["type"] in [SEARCH_TYPES.RECAP, SEARCH_TYPES.DOCKETS]:
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

    if cd["type"] in [SEARCH_TYPES.RECAP, SEARCH_TYPES.DOCKETS]:
        queries_list.extend(
            [
                *build_term_query(
                    "court_id.raw",
                    cd.get("court", "").split(),
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
        if len(selected_stats):
            queries_list.extend(
                build_term_query(
                    "status.raw",
                    selected_stats,
                )
            )

        queries_list.extend(
            [
                Q("match", cluster_child="opinion_cluster"),
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
            ]
        )

    return queries_list


def do_es_feed_query(
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
    match cd["type"]:
        case SEARCH_TYPES.RECAP:
            _, join_query = build_es_base_query(search_query, cd)
            # Eliminate items that lack the ordering field.
            s = build_child_docs_query(
                join_query, exclude_docs_for_empty_field="entry_date_filed"
            )
            s = search_query.query(s)
        case _:
            s, _ = build_es_base_query(search_query, cd)
    s = s.sort(build_sort_results(cd))
    response = s.extra(from_=0, size=rows).execute()
    return response


def build_full_join_es_queries(
    cd: CleanData,
    child_query_fields: dict[str, list[str]],
    parent_query_fields: list[str],
) -> tuple[QueryString | list, QueryString | None]:
    """Build a complete Elasticsearch query with both parent and child document
      conditions.

    :param cd: The query CleanedData
    :param child_query_fields: A dictionary mapping child fields document type.
    :param parent_query_fields: A list of fields for the parent document.
    :return: An Elasticsearch QueryString object.
    """

    q_should = []
    child_type = "recap_document"
    join_query = None
    if cd["type"] in [SEARCH_TYPES.RECAP, SEARCH_TYPES.DOCKETS]:
        # Build child filters.
        child_filters = build_has_child_filters(child_type, cd)

        # Build child text query.
        child_fields = child_query_fields["recap_document"]
        child_text_query = build_fulltext_query(
            child_fields, cd.get("q", ""), only_queries=True
        )

        # Build parent filters.
        parent_filters = build_join_es_filters(cd)
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
        if child_filters:
            child_filters = reduce(operator.iand, child_filters)
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

        if child_text_query or child_filters:
            _, query_hits_limit = get_child_top_hits_limit(cd, cd["type"])
            query = build_has_child_query(
                join_query,
                "recap_document",
                query_hits_limit,
                SEARCH_RECAP_CHILD_HL_FIELDS,
                get_child_sorting_key(cd),
            )
            q_should.append(query)

        # Build the parent filter and text queries.
        string_query = build_fulltext_query(
            parent_query_fields, cd.get("q", ""), only_queries=True
        )

        # Adds filter to the parent query to exclude results with no children
        if child_filters:
            parent_filters.append(
                Q(
                    "has_child",
                    type="recap_document",
                    score_mode="max",
                    query=Q("bool", filter=child_filters),
                )
            )
        parent_query = None
        match parent_filters, string_query:
            case [], []:
                pass
            case [], _:
                parent_query = Q(
                    "bool",
                    filter=Q("match", docket_child="docket"),
                    should=string_query,
                    minimum_should_match=1,
                )
            case _, []:
                parent_filters.extend([Q("match", docket_child="docket")])
                p_filters = reduce(operator.iand, parent_filters)
                parent_query = Q(
                    "bool",
                    filter=p_filters,
                )
            case _, _:
                parent_filters.extend([Q("match", docket_child="docket")])
                p_filters = reduce(operator.iand, parent_filters)
                parent_query = Q(
                    "bool",
                    filter=p_filters,
                    should=string_query,
                    minimum_should_match=1,
                )
        if parent_query:
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
    get_params: QueryDict, results: Page, search_type: str
) -> None:
    """Limit inner hits of has_child query results.

    :param get_params: The user search params.
    :param results: The Page object containing search results.
    :param search_type: The search type to perform.
    :return: None, the function updates the results in place.
    """

    hits_limit, _ = get_child_top_hits_limit(get_params, search_type)
    match search_type:
        case SEARCH_TYPES.OPINION:
            child_type = "opinion"
        case SEARCH_TYPES.RECAP | SEARCH_TYPES.DOCKETS:
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
