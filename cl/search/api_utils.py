import waffle
from django.conf import settings
from elasticsearch_dsl import Q
from rest_framework.exceptions import ParseError

from cl.lib import search_utils
from cl.lib.elasticsearch_utils import (
    build_es_main_query,
    do_collapse_count_query,
    do_count_query,
    do_es_api_query,
    merge_unavailable_fields_on_parent_document,
)
from cl.lib.scorched_utils import ExtraSolrInterface
from cl.lib.search_utils import map_to_docket_entry_sorting
from cl.search.constants import SEARCH_HL_TAG
from cl.search.documents import AudioDocument, OpinionDocument, PersonDocument
from cl.search.models import SEARCH_TYPES


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

    is_opinion_active = cd[
        "type"
    ] == SEARCH_TYPES.OPINION and waffle.flag_is_active(
        request, "o-es-search-api-active"
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
        main_query = do_es_api_query(
            search_query, cd, {"text": 500}, SEARCH_HL_TAG
        )
    else:
        main_query = search_utils.build_main_query(
            cd, highlight="text", facet=False, group=group
        )
        main_query["caller"] = "api_search"

    if cd["type"] == SEARCH_TYPES.RECAP:
        main_query["sort"] = map_to_docket_entry_sorting(main_query["sort"])

    if is_oral_argument_active or is_people_active or is_opinion_active:
        sl = ESList(
            main_query=main_query,
            offset=offset,
            page_size=page_size,
            type=cd["type"],
        )
    else:
        sl = SolrList(main_query=main_query, offset=offset, type=cd["type"])

    return sl


class ESList:
    """This class implements a yielding list object that fetches items from ES
    as they are queried.
    """

    def __init__(self, main_query, offset, page_size, type, length=None):
        super().__init__()
        self.main_query = main_query
        self.offset = offset
        self.page_size = page_size
        self.type = type
        self._item_cache = []
        self._length = length

    def __len__(self):
        if self._length is None:
            if self.type == SEARCH_TYPES.OPINION:
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
        # the API backwards compatible
        if self.type == SEARCH_TYPES.PEOPLE:
            merge_unavailable_fields_on_parent_document(
                results, self.type, "api"
            )

        # Pull the text snippet up a level
        for result in results:
            snippet = None
            if hasattr(result.meta, "highlight") and hasattr(
                result.meta.highlight, "text"
            ):
                snippet = result.meta.highlight["text"][0]
            elif hasattr(result, "text"):
                snippet = result["text"]

            result_dict = result.to_dict(skip_empty=False)
            result_dict["snippet"] = snippet
            self._item_cache.append(ResultObject(initial=result_dict))

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
        """Lightly override the append method so we get items duplicated in
        our cache.
        """
        self._item_cache.append(p_object)


class ResultObject:
    def __init__(self, initial=None):
        self.__dict__["_data"] = initial or {}

    def __getattr__(self, key):
        return self._data.get(key, None)

    def to_dict(self):
        return self._data
