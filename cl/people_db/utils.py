from django_elasticsearch_dsl.search import Search


async def make_title_str(person):
    """Make a nice title for somebody."""
    locations = ", ".join(
        {p.court.short_name async for p in person.positions.all() if p.court}
    )
    title = person.name_full
    if locations:
        title = f"{title} ({locations})"
    return title


def build_authored_opinions_query(
    search_query: Search,
    person_id: int,
) -> Search:
    """Build an ES query to retrieve Opinions related to a person.

    :param search_query: The ES DSL Search object.
    :param person_id: The ID of the person to filter cases by.
    :return: The ES DSL Search query.
    """

    search_query = search_query.query(
        "bool",
        filter=[{"match": {"cluster_child": "opinion"}}],
        should=[
            {"term": {"author_id": person_id}},
            {"term": {"panel_ids": person_id}},
        ],
        minimum_should_match=1,
    )
    search_query = search_query.source(
        [
            "id",
            "court_id",
            "caseName",
            "absolute_url",
            "court",
            "court_citation_string",
            "dateFiled",
            "docketNumber",
            "citeCount",
            "status",
            "citation",
            "sibling_ids",
        ]
    )
    search_query = search_query.sort("-dateFiled")
    extras = {
        "collapse": {
            "field": "cluster_id",
        },
        "size": 5,
        "track_total_hits": True,
    }
    search_query = search_query.extra(**extras)
    return search_query


def build_oral_arguments_heard(
    search_query: Search,
    person_id: int,
) -> Search:
    """Build an ES query to retrieve Oral Arguments related to a person.

    :param search_query: An ES DSL Search object.
    :param person_id: The ID of the person to filter cases by.
    :return: The ES DSL Search query.
    """

    search_query = search_query.filter("term", panel_ids=person_id)
    search_query = search_query.source(
        [
            "id",
            "absolute_url",
            "caseName",
            "court_id",
            "dateArgued",
            "docketNumber",
            "court_citation_string",
        ]
    )
    search_query = search_query.sort("-dateArgued")
    search_query = search_query.extra(size=5, track_total_hits=True)
    return search_query


def build_recap_cases_assigned_query(
    search_query: Search,
    person_id: int,
) -> Search:
    """Build an ES query to retrieve RECAP Cases related to a person.

    :param search_query: An ES DSL Search object.
    :param person_id: The ID of the person to filter cases by.
    :return: The ES DSL Search query.
    """

    search_query = search_query.query(
        "bool",
        filter=[{"match": {"docket_child": "docket"}}],
        should=[
            {"term": {"assigned_to_id": person_id}},
            {"term": {"referred_to_id": person_id}},
        ],
        minimum_should_match=1,
    )
    search_query = search_query.source(
        [
            "id",
            "docket_absolute_url",
            "caseName",
            "court_citation_string",
            "dateFiled",
            "docketNumber",
        ]
    )
    search_query = search_query.sort("-dateFiled")
    search_query = search_query.extra(size=5, track_total_hits=True)
    return search_query
