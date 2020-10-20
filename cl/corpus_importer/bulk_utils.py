from django.conf import settings
from django.core.paginator import Paginator

from cl.lib.scorched_utils import ExtraSolrInterface
from cl.lib.search_utils import build_main_query_from_query_string


def docket_pks_for_query(query_string):
    """Yield docket PKs for a query by iterating over the full result set

    :param query_string: The query to run as a URL-encoded string (typically
    starts with 'q='). E.g. 'q=foo&type=r&order_by=dateFiled+asc&court=dcd'
    :return: The next docket PK in the results
    """
    main_query = build_main_query_from_query_string(
        query_string,
        {"fl": ["docket_id"]},
        {"group": True, "facet": False, "highlight": False},
    )
    main_query["group.limit"] = 0
    main_query["sort"] = "dateFiled asc"
    si = ExtraSolrInterface(settings.SOLR_RECAP_URL, mode="r")
    search = si.query().add_extra(**main_query)
    si.conn.http_connection.close()
    page_size = 100
    paginator = Paginator(search, page_size)
    for page_number in paginator.page_range:
        page = paginator.page(page_number)
        for item in page:
            yield item["groupValue"]
