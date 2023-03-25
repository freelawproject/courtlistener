from datetime import date
from typing import Dict, List

from django_elasticsearch_dsl.search import Search
from elasticsearch_dsl import A, Q
from elasticsearch_dsl.query import Range

from cl.lib.types import CleanData
from cl.search.forms import ParentheticalSearchForm
from cl.search.models import PRECEDENTIAL_STATUS


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


def build_fulltext_query(field: str, value: str, query: str = "match") -> List:
    """Given the cleaned data from a form, return a Elastic Search string query or []
    https://www.elastic.co/guide/en/elasticsearch/reference/current/full-text-queries.html

    :param field: The name of the field to search in.
    :param value: The string value to search for.
    :param query: The type of Elastic Search query to use. Defaults to "match".
    :return: A list of Elastic Search queries. If the "value" param is
    empty or None, returns an empty list.
    """
    queries = ["match", "match_phrase", "query_string"]
    assert query in queries, f"'{query}' is not an allowed query."
    if value:
        return [Q(query, **{field: value})]
    return []


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
        "score desc": {"score": "desc"},
        "dateFiled desc": {"described_opinion_cluster_date_filed": "desc"},
        "dateFiled asc": {"described_opinion_cluster_date_filed": "asc"},
    }
    order_by = cd.get("order_by")
    if order_by and order_by in order_by_map:
        return order_by_map[order_by]

    # Default sort by score in descending order
    return {"score": "desc"}


def build_es_queries(cd: CleanData) -> List:
    """Builds elasticsearch queries based on the CleanData object.

    :param cd: An object containing cleaned user data.
    :return: The list of Elasticsearch queries built.
    """

    queries_list = []

    # Build daterange query
    queries_list.extend(
        build_daterange_query(
            "described_opinion_cluster_date_filed",
            cd.get("filed_before", ""),
            cd.get("filed_after", ""),
        )
    )

    # Build court terms filter
    queries_list.extend(
        build_terms_query(
            "described_opinion_cluster_docket_court_id",
            cd.get("court", "").split(),
        )
    )

    # Build precedential status terms filter
    stat_list = get_precedential_status_values(cd)
    queries_list.extend(
        build_terms_query(
            "described_opinion_cluster_precedential_status",
            stat_list,
        )
    )

    # Build fulltext query
    queries_list.extend(build_fulltext_query("text", cd.get("q", "")))

    # Build docket number term query
    queries_list.extend(
        build_term_query(
            "described_opinion_cluster_docket_number",
            cd.get("docket_number", ""),
        )
    )

    # Build opinion id term query
    queries_list.extend(
        build_term_query("described_opinion_id", cd.get("opinion_id", ""))
    )

    return queries_list


def group_search_results(
    search: Search, group_by: str, order_by: str, size: int
) -> None:
    """Group search results by a specified field and return top hits for each
    group.

    :param search: The elasticsearch Search object representing the query.
    :param group_by: The field name to group the results by.
    :param order_by: The field name to use for sorting the top hits.
    :param  size: The number of top hits to return for each group.
    :return: None, results are returned as part of the Elasticsearch search object.
    """

    aggregation = A("terms", field=group_by)
    sub_aggregation = A(
        "top_hits", size=size, sort={order_by: {"order": "desc"}}
    )
    aggregation.bucket("grouped_by_group_id", sub_aggregation)
    search.aggs.bucket("groups", aggregation)


def get_precedential_status_values(cd: CleanData) -> list[str]:
    """Convert precedential_status from clean data to a list of values for
    use in an elastic search query.
    e.g: stat_Precedential=on, stat_Errata=on
    to: ["Published", "Errata"]

    :param cd: The form CleanData
    :return: A list of precedential_status to query.
    """
    status_list = []
    status_names_to_values = {
        name: value for value, name in PRECEDENTIAL_STATUS.NAMES
    }
    for stat_v in dict(PRECEDENTIAL_STATUS.NAMES).values():
        if cd.get(f"stat_{stat_v}"):
            status_value = status_names_to_values.get(stat_v, "")
            status_list.append(status_value)

    return status_list


def make_stats_es_facets(search_form: ParentheticalSearchForm):
    """Create facets for precedential_status.

    :param search_form: The ParentheticalSearchForm
    :return: A list of faceted fields.
    """
    # TODO retrieve facets from ES.
    facet_fields = []
    for field in search_form:
        if not field.html_name.startswith("stat_"):
            continue
        facet_fields.append(field)
    return facet_fields
