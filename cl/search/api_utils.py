import waffle
from django.conf import settings
from elasticsearch_dsl import Q
from elasticsearch_dsl.response import Response
from elasticsearch_dsl.utils import AttrList
from rest_framework.exceptions import ParseError

from cl.lib import search_utils
from cl.lib.elasticsearch_utils import (
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
from cl.search.models import SEARCH_TYPES
from cl.search.types import ESCursor


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
    is_recap_active = (
        cd["type"] == SEARCH_TYPES.RECAP and request.version == "v4"
    )

    if is_oral_argument_active:
        search_query = AudioDocument.search()
    elif is_people_active:
        search_query = PersonDocument.search()
    elif is_opinion_active:
        search_query = OpinionDocument.search()
    elif is_recap_active:
        search_query = DocketDocument.search()
    else:
        search_query = None

    if search_query and (is_people_active or is_oral_argument_active):
        (
            main_query,
            child_docs_count_query,
            top_hits_limit,
        ) = build_es_main_query(search_query, cd)
    elif search_query and (is_opinion_active or is_recap_active):
        if request.version == "v3":
            cd["highlight"] = True
        highlighting_fields = {}
        if cd["type"] == SEARCH_TYPES.OPINION:
            highlighting_fields = {"text": 500}
        main_query = do_es_api_query(
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

    if (
        is_oral_argument_active
        or is_people_active
        or is_opinion_active
        or is_recap_active
    ):
        sl = ESList(
            main_query=main_query,
            offset=offset,
            page_size=page_size,
            clean_data=cd,
            version=request.version,
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
        version="v3",
    ):
        super().__init__()
        self.main_query = main_query
        self.offset = offset
        self.page_size = page_size
        self.clean_data = clean_data
        self._item_cache = []
        self._length = length
        self._version = version

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

        if self._version == "v4":
            limit_inner_hits({}, results, self.clean_data["type"])
            set_results_highlights(results, self.clean_data["type"])

        # Merge unavailable fields in ES by pulling data from the DB to make
        # the API backwards compatible or retrieves the snippet from the DB
        # when highlighting is disabled.
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
                        ESResultObject(initial=child_doc["_source"])
                    )
                result["child_docs"] = child_result_objects

            # Send the object instead the JSON.
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

    def __init__(
        self, main_query, page_size, search_after, clean_data, version="v3"
    ):
        self.main_query = main_query
        self.page_size = page_size
        self.search_after = search_after
        self.clean_data = clean_data
        self.version = version
        self._item_cache = []
        self.results = None
        self.reverse = None
        self.cursor = None

    def set_pagination(self, cursor, page_size):

        self.cursor = cursor
        if self.cursor is not None:
            (self.search_after, self.reverse) = self.cursor

        # Return one extra document beyond the page size, so we're able to
        # determine if there are more documents and decide whether to display a
        # next or previous page link.
        self.page_size = page_size + 1

    def get_paginated_results(self):
        """Executes the search query with pagination settings and processes
        the results.
        """
        if self.search_after:
            self.main_query = self.main_query.extra(
                search_after=self.search_after
            )

        self.main_query = self.main_query[: self.page_size]

        toggle_sort = False
        if self.reverse:
            # Toggle the original sorting key to handle backward pagination
            toggle_sort = True

        default_sorting = build_sort_results(
            self.clean_data, toggle_sort, "v4"
        )
        default_unique_order = {
            "type": self.clean_data["type"],
            "order_by": "docket_id desc",
        }
        unique_sorting = build_sort_results(
            default_unique_order, toggle_sort, "v4"
        )
        self.main_query = self.main_query.sort(default_sorting, unique_sorting)
        self.results = self.main_query.execute()
        self.process_results(self.results)
        return self.results

    def process_results(self, results):
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
                        ESResultObject(initial=child_doc["_source"])
                    )
                result["child_docs"] = child_result_objects

        if self.reverse:
            # If doing backward pagination, reverse the results of the current
            # page to maintain consistency of the results on the page,
            # because the original order is inverse when paginating backwards.
            self.results.hits.reverse()

    def _get_search_after_key(self, position):
        if self.results and len(self.results) > 0:
            limited_results = limit_api_results_to_page(
                self.results.hits, self.cursor
            )
            last_result = limited_results[position]
            return last_result.meta.sort
        return None

    def get_search_after_sort_key(self):
        """Retrieves the sort key from the last item in the current page to
        use for the next page's search_after parameter.
        """
        last_result_in_page = -1
        return self._get_search_after_key(last_result_in_page)

    def get_reverse_search_after_sort_key(self):
        """Retrieves the sort key from the last item in the current page to
        use for the next page's search_after parameter.
        """
        first_result_in_page = 0
        return self._get_search_after_key(first_result_in_page)


class ResultObject:
    def __init__(self, initial=None):
        self.__dict__["_data"] = initial or {}

    def __getattr__(self, key):
        return self._data.get(key, None)

    def to_dict(self):
        return self._data


class ESResultObject(ResultObject):

    def __getattr__(self, key):
        return getattr(self._data, key, None)


def limit_api_results_to_page(
    results: Response | AttrList, cursor: ESCursor
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

    reverse = False
    if cursor is not None:
        search_after, reverse = cursor
    if reverse:
        # Limit results in page starting from the last item.
        return results[-settings.SEARCH_API_PAGE_SIZE :]
    else:
        # Limit results in page starting from the first item.
        return results[: settings.SEARCH_API_PAGE_SIZE]
