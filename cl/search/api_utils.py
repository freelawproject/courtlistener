import logging
from collections import defaultdict

from django.conf import settings
from elasticsearch.exceptions import ApiError, RequestError, TransportError
from elasticsearch_dsl import MultiSearch, Q
from elasticsearch_dsl.response import Response
from elasticsearch_dsl.utils import AttrList
from rest_framework.exceptions import ParseError

from cl.lib.elasticsearch_utils import (
    build_cardinality_count,
    build_es_main_query,
    build_sort_results,
    clean_count_query,
    do_collapse_count_query,
    do_count_query,
    do_es_api_query,
    limit_inner_hits,
    merge_unavailable_fields_on_parent_document,
    set_child_docs_and_score,
    set_results_highlights,
)
from cl.lib.search_utils import store_search_api_query
from cl.search.constants import SEARCH_HL_TAG, cardinality_query_unique_ids
from cl.search.documents import (
    AudioDocument,
    DocketDocument,
    ESRECAPDocument,
    OpinionClusterDocument,
    OpinionDocument,
    PersonDocument,
)
from cl.search.exception import ElasticBadRequestError, ElasticServerError
from cl.search.models import SEARCH_TYPES, SearchQuery
from cl.search.types import ESCursor

logger = logging.getLogger(__name__)


def get_object_list(request, cd, paginator):
    """Perform the search engine work"""
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

    use_default_query = False
    match cd["type"]:
        case SEARCH_TYPES.ORAL_ARGUMENT:
            search_query = AudioDocument.search()
            use_default_query = True
        case SEARCH_TYPES.PEOPLE:
            search_query = PersonDocument.search()
            use_default_query = True
        case SEARCH_TYPES.OPINION:
            search_query = OpinionDocument.search()
        case SEARCH_TYPES.RECAP | SEARCH_TYPES.DOCKETS:
            search_query = ESRECAPDocument.search()
        case _:
            raise ElasticBadRequestError("Unsupported search type.")

    if use_default_query:
        main_query, _, _ = build_es_main_query(search_query, cd)
    else:
        cd["highlight"] = True
        highlighting_fields = {}
        if cd["type"] == SEARCH_TYPES.OPINION:
            highlighting_fields = {"text": 500}
        elif cd["type"] == SEARCH_TYPES.RECAP:
            highlighting_fields = {"plain_text": 500}
        main_query, _ = do_es_api_query(
            search_query,
            cd,
            highlighting_fields,
            SEARCH_HL_TAG,
            request.version,
        )

    sl = ESList(
        request=request,
        main_query=main_query,
        offset=offset,
        page_size=page_size,
        type=cd["type"],
    )
    return sl


class ESList:
    """This class implements a yielding list object that fetches items from ES
    as they are queried.
    """

    def __init__(
        self, request, main_query, offset, page_size, type, length=None
    ):
        super().__init__()
        self.request = request
        self.main_query = main_query
        self.offset = offset
        self.page_size = page_size
        self.type = type
        self._item_cache = []
        self._length = length

    def __len__(self):
        if self._length is None:
            if self.type in [SEARCH_TYPES.OPINION, SEARCH_TYPES.DOCKETS]:
                query = Q(self.main_query.to_dict(count=True)["query"])
                self._length = do_collapse_count_query(
                    self.type, self.main_query, query
                )
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

        error_to_raise = None
        try:
            results = self.main_query.execute()
        except (TransportError, ConnectionError, RequestError) as e:
            error_to_raise = ElasticServerError
        except ApiError as e:
            if "Failed to parse query" in str(e):
                error_to_raise = ElasticBadRequestError
            else:
                logger.error("Multi-search API Error: %s", e)
                error_to_raise = ElasticServerError

        # Store search query.
        store_search_api_query(
            request=self.request,
            failed=bool(error_to_raise),
            query_time=results.took if not error_to_raise else None,
            engine=SearchQuery.ELASTICSEARCH,
        )

        if error_to_raise:
            raise error_to_raise()

        # Merge unavailable fields in ES by pulling data from the DB to make
        # the API backwards compatible for People.
        merge_unavailable_fields_on_parent_document(
            results,
            self.type,
            "v3",
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


class CursorESList:
    """Handles the execution and postprocessing of Elasticsearch queries, as
    well as the pagination logic for cursor-based pagination.
    """

    cardinality_base_document = {
        SEARCH_TYPES.RECAP: DocketDocument,
        SEARCH_TYPES.DOCKETS: DocketDocument,
        SEARCH_TYPES.RECAP_DOCUMENT: DocketDocument,
        SEARCH_TYPES.OPINION: OpinionClusterDocument,
        SEARCH_TYPES.PEOPLE: PersonDocument,
        SEARCH_TYPES.ORAL_ARGUMENT: AudioDocument,
    }

    def __init__(
        self,
        main_query,
        child_docs_query,
        page_size,
        search_after,
        clean_data,
        request,
    ):
        self.main_query = main_query
        self.child_docs_query = child_docs_query
        self.page_size = page_size
        self.search_after = search_after
        self.clean_data = clean_data
        self.request = request
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

        :return: A four-tuple containing a list of defaultdicts with the results,
        the number of hits returned by the main query, a response object
        related to the main query's cardinality count, and a response object
        related to the child query's cardinality count, if available.
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
        main_count_query = clean_count_query(self.main_query)
        unique_field = cardinality_query_unique_ids[self.clean_data["type"]]
        cardinality_query = build_cardinality_count(
            main_count_query, unique_field
        )

        # Build a cardinality query to count child documents.
        child_cardinality_query = None
        child_cardinality_count_response = None
        if (
            self.child_docs_query
            and self.clean_data["type"] == SEARCH_TYPES.RECAP
        ):
            child_unique_field = cardinality_query_unique_ids[
                SEARCH_TYPES.RECAP_DOCUMENT
            ]
            search_document = self.cardinality_base_document[
                self.clean_data["type"]
            ]
            child_count_query = search_document.search().query(
                self.child_docs_query
            )
            child_cardinality_query = build_cardinality_count(
                child_count_query, child_unique_field
            )

        error_to_raise = None
        try:
            multi_search = MultiSearch()
            multi_search = multi_search.add(self.main_query).add(
                cardinality_query
            )
            # If a cardinality query is available for the search_type, add it
            # to the multi-search query.
            if (
                child_cardinality_query
                and self.clean_data["type"] == SEARCH_TYPES.RECAP
            ):
                multi_search = multi_search.add(child_cardinality_query)

            responses = multi_search.execute()
            self.results = responses[0]
            cardinality_count_response = responses[1]
            if child_cardinality_query:
                child_cardinality_count_response = responses[2]
        except (TransportError, ConnectionError, RequestError) as e:
            error_to_raise = ElasticServerError
        except ApiError as e:
            if "Failed to parse query" in str(e):
                error_to_raise = ElasticBadRequestError
            else:
                logger.error("Multi-search API Error: %s", e)
                error_to_raise = ElasticServerError

        # Store search query.
        store_search_api_query(
            request=self.request,
            failed=bool(error_to_raise),
            query_time=self.results.took if not error_to_raise else None,
            engine=SearchQuery.ELASTICSEARCH,
        )
        if error_to_raise:
            raise error_to_raise()

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
            "v4",
            self.clean_data["highlight"],
        )
        set_child_docs_and_score(results, merge_score=True)

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
        unique_field = cardinality_query_unique_ids[self.clean_data["type"]]
        # Use a document unique field as a unique sorting key for the current
        # search type.
        default_unique_order.update(
            {
                "order_by": f"{unique_field} desc",
            }
        )

        unique_sorting = build_sort_results(
            default_unique_order, self.reverse, "v4"
        )
        return default_sorting, unique_sorting


class ResultObject:
    def __init__(self, initial=None):
        self.__dict__["_data"] = initial or {}

    def __getattr__(self, key):
        return self._data.get(key, None)

    def to_dict(self):
        return self._data


def limit_api_results_to_page(
    results: list[defaultdict], cursor: ESCursor | None
) -> list[defaultdict]:
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
