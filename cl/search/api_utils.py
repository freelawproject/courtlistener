import logging
from collections import defaultdict

import waffle
from django.conf import settings
from elasticsearch.exceptions import ApiError, RequestError, TransportError
from elasticsearch_dsl import MultiSearch, Q
from elasticsearch_dsl.response import Response
from elasticsearch_dsl.utils import AttrList
from rest_framework.exceptions import ParseError

from cl.lib import search_utils
from cl.lib.elasticsearch_utils import (
    build_cardinality_count,
    build_es_main_query,
    build_sort_results,
    do_collapse_count_query,
    do_count_query,
    do_es_api_query,
    limit_inner_hits,
    merge_unavailable_fields_on_parent_document,
    set_results_highlights,
)
from cl.lib.scorched_utils import ExtraSolrInterface
from cl.lib.search_utils import map_to_docket_entry_sorting
from cl.search.constants import SEARCH_HL_TAG
from cl.search.documents import (
    AudioDocument,
    DocketDocument,
    OpinionDocument,
    PersonDocument,
)
from cl.search.exception import ElasticBadRequestError, ElasticServerError
from cl.search.models import SEARCH_TYPES
from cl.search.types import ESCursor

logger = logging.getLogger(__name__)


class ResultObject:
    def __init__(self, initial=None):
        self.__dict__["_data"] = initial or {}

    def __getattr__(self, key):
        return self._data.get(key, None)

    def to_dict(self):
        return self._data


def get_object_list(request, cd, paginator):
    """Perform the Solr work"""
    # Set the offset value
    try:
        page_number = int(request.GET.get(paginator.page_query_param, 1))
    except ValueError:
        raise ParseError(
            f"Invalid page number: {request.GET.get(paginator.page_query_param)}"
        )
    page_size = paginator.get_page_size(request)
    # Assume page_size = 20, then: 1 --> 0, 2 --> 20, 3 --> 40
    offset = max(0, (page_number - 1) * page_size)
    group = False
    if cd["type"] == SEARCH_TYPES.DOCKETS:
        group = True

    is_oral_argument_active = cd[
        "type"
    ] == SEARCH_TYPES.ORAL_ARGUMENT and waffle.flag_is_active(
        request, "oa-es-activate"
    )
    is_people_active = cd[
        "type"
    ] == SEARCH_TYPES.PEOPLE and waffle.flag_is_active(request, "p-es-active")
    is_opinion_active = cd["type"] == SEARCH_TYPES.OPINION and (
        waffle.flag_is_active(request, "o-es-search-api-active")
    )

    if is_oral_argument_active:
        search_query = AudioDocument.search()
    elif is_people_active:
        search_query = PersonDocument.search()
    elif is_opinion_active:
        search_query = OpinionDocument.search()
    else:
        search_query = None

    if search_query and (is_people_active or is_oral_argument_active):
        (
            main_query,
            child_docs_count_query,
            top_hits_limit,
        ) = build_es_main_query(search_query, cd)
    elif search_query and is_opinion_active:
        if request.version == "v3":
            cd["highlight"] = True
        highlighting_fields = {}
        if cd["type"] == SEARCH_TYPES.OPINION:
            highlighting_fields = {"text": 500}
        main_query, _ = do_es_api_query(
            search_query,
            cd,
            highlighting_fields,
            SEARCH_HL_TAG,
            request.version,
        )
    else:
        main_query = search_utils.build_main_query(
            cd, highlight="text", facet=False, group=group
        )
        main_query["caller"] = "api_search"

    if cd["type"] == SEARCH_TYPES.RECAP and request.version == "v3":
        main_query["sort"] = map_to_docket_entry_sorting(main_query["sort"])

    if is_oral_argument_active or is_people_active or is_opinion_active:
        sl = ESList(
            main_query=main_query,
            offset=offset,
            page_size=page_size,
            clean_data=cd,
        )
    else:
        sl = SolrList(main_query=main_query, offset=offset, type=cd["type"])

    return sl


class ESList:
    """This class implements a yielding list object that fetches items from ES
    as they are queried.
    """

    def __init__(
        self,
        main_query,
        offset,
        page_size,
        clean_data,
        length=None,
    ):
        super().__init__()
        self.main_query = main_query
        self.offset = offset
        self.page_size = page_size
        self.clean_data = clean_data
        self._item_cache = []
        self._length = length

    def __len__(self):
        if self._length is None:
            if self.clean_data["type"] == SEARCH_TYPES.OPINION:
                query = Q(self.main_query.to_dict(count=True)["query"])
                self._length = do_collapse_count_query(self.main_query, query)
            else:
                self._length = do_count_query(self.main_query)
        return self._length

    def __iter__(self):
        # Iterate over the results returned by the query, up to the specified
        # page_size.
        total_items = min(len(self), self.page_size)
        for item in range(0, total_items):
            try:
                yield self._item_cache[item]
            except IndexError:
                yield self.__getitem__(item)

    def __getitem__(self, item):
        # Offset is handled by Elasticsearch DSL based on this slicing.
        self.main_query = self.main_query[
            self.offset : self.offset + self.page_size
        ]
        results = self.main_query.execute()

        # Merge unavailable fields in ES by pulling data from the DB to make
        # the API backwards compatible for People.
        merge_unavailable_fields_on_parent_document(
            results,
            self.clean_data["type"],
            "api",
            self.clean_data["highlight"],
        )
        for result in results:
            self._item_cache.append(result)

        # Now, assuming our _item_cache is all set, we just get the item.
        if isinstance(item, slice):
            s = slice(
                item.start - int(self.offset),
                item.stop - int(self.offset),
                item.step,
            )
            return self._item_cache[s]
        else:
            # Not slicing.
            try:
                return self._item_cache[item]
            except IndexError:
                # No results!
                return []

    def append(self, p_object):
        """Lightly override the append method so we get items duplicated in
        our cache.
        """
        self._item_cache.append(p_object)


class SolrList:
    """This implements a yielding list object that fetches items as they are
    queried.
    """

    def __init__(self, main_query, offset, type, length=None):
        super().__init__()
        self.main_query = main_query
        self.offset = offset
        self.type = type
        self._item_cache = []
        if self.type == SEARCH_TYPES.OPINION:
            self.conn = ExtraSolrInterface(settings.SOLR_OPINION_URL, mode="r")
        elif self.type == SEARCH_TYPES.ORAL_ARGUMENT:
            self.conn = ExtraSolrInterface(settings.SOLR_AUDIO_URL, mode="r")
        elif self.type in [SEARCH_TYPES.RECAP, SEARCH_TYPES.DOCKETS]:
            self.conn = ExtraSolrInterface(settings.SOLR_RECAP_URL, mode="r")
        elif self.type == SEARCH_TYPES.PEOPLE:
            self.conn = ExtraSolrInterface(settings.SOLR_PEOPLE_URL, mode="r")
        self._length = length

    def __len__(self):
        if self._length is None:
            mq = self.main_query.copy()  # local copy for manipulation
            mq["caller"] = "api_search_count"
            count = self.conn.query().add_extra(**mq).count()
            self._length = count
        return self._length

    def __iter__(self):
        for item in range(0, len(self)):
            try:
                yield self._item_cache[item]
            except IndexError:
                yield self.__getitem__(item)

    def __getitem__(self, item):
        self.main_query["start"] = self.offset
        r = self.conn.query().add_extra(**self.main_query).execute()
        self.conn.conn.http_connection.close()
        if r.group_field is None:
            # Pull the text snippet up a level
            for result in r.result.docs:
                result["snippet"] = "&hellip;".join(
                    result["solr_highlights"]["text"]
                )
                self._item_cache.append(ResultObject(initial=result))
        else:
            # Flatten group results, and pull up the text snippet as above.
            for group in getattr(r.groups, r.group_field)["groups"]:
                for doc in group["doclist"]["docs"]:
                    doc["snippet"] = "&hellip;".join(
                        doc["solr_highlights"]["text"]
                    )
                    self._item_cache.append(ResultObject(initial=doc))

        # Now, assuming our _item_cache is all set, we just get the item.
        if isinstance(item, slice):
            s = slice(
                item.start - int(self.offset),
                item.stop - int(self.offset),
                item.step,
            )
            return self._item_cache[s]
        else:
            # Not slicing.
            try:
                return self._item_cache[item]
            except IndexError:
                # No results!
                return []

    def append(self, p_object):
        """Lightly override the append method, so we get items duplicated in
        our cache.
        """
        self._item_cache.append(p_object)


class CursorESList:
    """Handles the execution and postprocessing of Elasticsearch queries, as
    well as the pagination logic for cursor-based pagination.
    """

    cardinality_query = {
        SEARCH_TYPES.RECAP: ("docket_id", DocketDocument),
        SEARCH_TYPES.DOCKETS: ("docket_id", DocketDocument),
        SEARCH_TYPES.RECAP_DOCUMENT: ("id", DocketDocument),
    }

    def __init__(
        self,
        main_query,
        child_docs_query,
        page_size,
        search_after,
        clean_data,
        version="v3",
    ):
        self.main_query = main_query
        self.child_docs_query = child_docs_query
        self.page_size = page_size
        self.search_after = search_after
        self.clean_data = clean_data
        self.version = version
        self.cursor = None
        self.results = None
        self.reverse = False

    def set_pagination(self, cursor: ESCursor | None, page_size: int) -> None:

        self.cursor = cursor
        if self.cursor is not None:
            self.reverse = self.cursor.reverse
            self.search_after = self.cursor.search_after

        # Return one extra document beyond the page size, so we're able to
        # determine if there are more documents and decide whether to display a
        # next or previous page link.
        self.page_size = page_size + 1

    def get_paginated_results(
        self,
    ) -> tuple[list[defaultdict], int, Response, Response | None]:
        """Executes the search query with pagination settings and processes
        the results.

        :return: A four-tuple containing a list of ESResultObjects, the number
        of hits returned by the main query, a response object related to the
        main query's cardinality count, and a response object related to the
        child query's cardinality count, if available.
        """
        if self.search_after:
            self.main_query = self.main_query.extra(
                search_after=self.search_after
            )

        # Main query parameters
        self.main_query = self.main_query[: self.page_size]
        default_sorting, unique_sorting = self.get_api_query_sorting()
        self.main_query = self.main_query.sort(default_sorting, unique_sorting)

        # Cardinality query parameters
        query = Q(self.main_query.to_dict(count=True)["query"])
        unique_field, search_document = self.cardinality_query[
            self.clean_data["type"]
        ]
        base_search = search_document.search()
        cardinality_query = build_cardinality_count(
            base_search, query, unique_field
        )

        # Build a cardinality query to count child documents.
        child_cardinality_query = None
        child_cardinality_count_response = None
        if self.child_docs_query:
            child_unique_field, _ = self.cardinality_query[
                SEARCH_TYPES.RECAP_DOCUMENT
            ]
            child_cardinality_query = build_cardinality_count(
                base_search, self.child_docs_query, child_unique_field
            )
        try:
            multi_search = MultiSearch()
            multi_search = multi_search.add(self.main_query).add(
                cardinality_query
            )
            # If a cardinality query is available for the search_type, add it
            # to the multi-search query.
            if child_cardinality_query:
                multi_search = multi_search.add(child_cardinality_query)

            responses = multi_search.execute()
            self.results = responses[0]
            cardinality_count_response = responses[1]
            if child_cardinality_query:
                child_cardinality_count_response = responses[2]
        except (TransportError, ConnectionError, RequestError) as e:
            raise ElasticServerError()
        except ApiError as e:
            if "Failed to parse query" in str(e):
                raise ElasticBadRequestError()
            else:
                logger.error("Multi-search API Error: %s", e)
                raise ElasticServerError()
        self.process_results(self.results)

        main_query_hits = self.results.hits.total.value
        es_results_items = [
            defaultdict(lambda: None, result.to_dict(skip_empty=False))
            for result in self.results
        ]
        return (
            es_results_items,
            main_query_hits,
            cardinality_count_response,
            child_cardinality_count_response,
        )

    def process_results(self, results: Response) -> None:
        """Processes the raw results from ES for handling inner hits,
        highlighting and merging of unavailable fields.
        """

        limit_inner_hits({}, results, self.clean_data["type"])
        set_results_highlights(results, self.clean_data["type"])
        merge_unavailable_fields_on_parent_document(
            results,
            self.clean_data["type"],
            "api",
            self.clean_data["highlight"],
        )
        for result in results:
            child_result_objects = []
            if hasattr(result, "child_docs"):
                for child_doc in result.child_docs:
                    child_result_objects.append(
                        defaultdict(
                            lambda: None, child_doc["_source"].to_dict()
                        )
                    )
                result["child_docs"] = child_result_objects

        if self.reverse:
            # If doing backward pagination, reverse the results of the current
            # page to maintain consistency of the results on the page,
            # because the original order is inverse when paginating backwards.
            self.results.hits.reverse()

    def _get_search_after_key(self, index_position: int) -> AttrList | None:
        if self.results and len(self.results) > 0:
            limited_results = limit_api_results_to_page(
                self.results.hits, self.cursor
            )
            last_result = limited_results[index_position]
            return last_result.meta.sort
        return None

    def get_search_after_sort_key(self) -> AttrList | None:
        """Retrieves the sort key from the last item in the current page to
        use for the next page's search_after parameter.
        """
        last_result_in_page = -1
        return self._get_search_after_key(last_result_in_page)

    def get_reverse_search_after_sort_key(self) -> AttrList | None:
        """Retrieves the sort key from the last item in the current page to
        use for the next page's search_after parameter.
        """
        first_result_in_page = 0
        return self._get_search_after_key(first_result_in_page)

    def get_api_query_sorting(self):
        """Build the sorting settings for an ES query to work with the
        'search_after' pagination. Two sorting keys are returned: the default
        sorting requested by the user and a unique sorting key based on a
        unique field across documents, acting as a tiebreaker for the default
        sorting.

        :return: A tuple containing default_sorting and unique_sorting
        settings.
        """

        # Toggle the original sorting key to handle backward pagination
        default_sorting = build_sort_results(
            self.clean_data, self.reverse, "v4"
        )
        default_unique_order = {
            "type": self.clean_data["type"],
        }
        match self.clean_data["type"]:
            case SEARCH_TYPES.RECAP_DOCUMENT:
                # Use the 'id' field as a unique sorting key for the 'rd'
                # search type.
                default_unique_order.update(
                    {
                        "order_by": "id desc",
                    }
                )
            case _:
                # Use the 'docket_id' field as a unique sorting key for the
                # 'd' and 'r' search type.
                default_unique_order.update(
                    {
                        "order_by": "docket_id desc",
                    }
                )

        unique_sorting = build_sort_results(
            default_unique_order, self.reverse, "v4"
        )
        return default_sorting, unique_sorting


def limit_api_results_to_page(
    results: Response | AttrList, cursor: ESCursor | None
) -> Response | AttrList:
    """In ES Cursor pagination, an additional document is returned in each
    query response to determine whether to display the next page or previous
    pages. Here we limit the API results to the number defined in
    settings for a single page, according to the navigation action being
    performed.

    :param results: The results returned by ES.
    :param cursor: A ESCursor instance containing the "search_after" parameter
     and a boolean "reverse" indicating if going backwards.
    :return: A slice of the results list, limited to the number of items as
    specified by the SEARCH_API_PAGE_SIZE.
    """

    reverse = cursor.reverse if cursor else False
    if reverse:
        # Limit results in page starting from the last item.
        return results[-settings.SEARCH_API_PAGE_SIZE :]

    # First page or going forward, limit results on the page starting from the
    # first item.
    return results[: settings.SEARCH_API_PAGE_SIZE]
