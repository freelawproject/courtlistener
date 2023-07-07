import operator
import re
from datetime import date
from functools import reduce
from typing import Dict, List

from django.core.paginator import Page
from django_elasticsearch_dsl.search import Search
from elasticsearch_dsl import A, Q
from elasticsearch_dsl.query import QueryString, Range

from cl.lib.types import CleanData
from cl.search.models import SEARCH_TYPES, Court


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


def build_fulltext_query(field: str, value: str) -> QueryString | None:
    """Given the cleaned data from a form, return a Elastic Search string query or []
    https://www.elastic.co/guide/en/elasticsearch/reference/current/full-text-queries.html

    :param field: The name of the field to search in.
    :param value: The string value to search for.
    :return: A Elasticsearch QueryString or None if the "value" param is empty.
    """

    if value:
        # In Elasticsearch, the colon (:) character is used to separate the
        # field name and the field value in a query.
        # To avoid parsing errors escape any colon characters in the value
        # parameter with a backslash.
        if "docketNumber:" in value:
            docket_number_match = re.search("docketNumber:([^ ]+)", value)
            if docket_number_match:
                docket_number = docket_number_match.group(1)
                docket_number = docket_number.replace(":", r"\:")
                value = re.sub(
                    r"docketNumber:([^ ]+)",
                    f"docketNumber:{docket_number}",
                    value,
                )
        return Q("query_string", query=value, fields=[field])
    return None


def build_term_query(field: str, value: str) -> List:
    """Given field name and value, return Elastic Search term query or [].
    "term" Returns documents that contain an exact term in a provided field
    NOTE: Use it only whe you want an exact match, avoid using this with text fields
    https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-term-query.html

    :param field: elasticsearch index fieldname
    :param value: term to find
    :return: Empty list or list with DSL Match query
    """
    if value:
        return [Q("term", **{field: value})]
    return []


def build_terms_query(field: str, value: List) -> List:
    """Given field name and list of values, return Elastic Search term query or [].
    "terms" Returns documents that contain one or more exact terms in a provided field.

    https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-terms-query.html
    :param field: elasticsearch index fieldname
    :param value: term to find
    :return: Empty list or list with DSL Match query
    """

    # Remove elements that evaluate to False, like ""
    value = list(filter(None, value))
    if value:
        return [Q("terms", **{field: value})]
    return []


def build_sort_results(cd: CleanData) -> Dict:
    """Given cleaned data, find order_by value and return dict to use with
    ElasticSearch sort

    :param cd: The user input CleanedData
    :return: The short dict.
    """

    order_by_map = {
        "score desc": {"score": {"order": "desc"}},
        "dateFiled desc": {"dateFiled": {"order": "desc"}},
        "dateFiled asc": {"dateFiled": {"order": "asc"}},
    }
    order_by = cd.get("order_by")
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

    # Build daterange query
    queries_list.extend(
        build_daterange_query(
            "dateFiled",
            cd.get("filed_before", ""),
            cd.get("filed_after", ""),
        )
    )

    # Build court terms filter
    queries_list.extend(
        build_terms_query(
            "court_id",
            cd.get("court", "").split(),
        )
    )

    # Build docket number term query
    queries_list.extend(
        build_term_query(
            "docketNumber",
            cd.get("docket_number", ""),
        )
    )

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

    filters = build_es_filters(cd)
    string_query = build_fulltext_query("representative_text", cd.get("q", ""))
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

    return search_query, total_query_results, top_hits_limit


def set_results_highlights(results: Page, search_type: str) -> None:
    """Sets the highlights for each search result in a Page object by updating
    related fields in _source dict.

    :param results: The Page object containing search results.
    :param search_type: The search type to perform.
    :return: None, the function updates the results in place.
    """
    for result in results.object_list:
        top_hits = result.grouped_by_opinion_cluster_id.hits.hits
        for hit in top_hits:
            if hasattr(hit, "highlight"):
                highlighted_fields = [
                    k for k in dir(hit.highlight) if not k.startswith("_")
                ]
                for highlighted_field in highlighted_fields:
                    highlight = hit.highlight[highlighted_field][0]
                    hit["_source"][highlighted_field] = highlight


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
