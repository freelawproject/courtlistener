from base64 import b64decode, b64encode
from collections import defaultdict
from urllib.parse import parse_qs, urlencode

from django.conf import settings
from django.core.paginator import InvalidPage
from rest_framework.exceptions import NotFound
from rest_framework.pagination import BasePagination, PageNumberPagination
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.utils.urls import replace_query_param

from cl.search.api_utils import CursorESList
from cl.search.models import SEARCH_TYPES
from cl.search.types import ESCursor


class ShallowOnlyPageNumberPagination(PageNumberPagination):
    """A paginator that blocks deep pagination

    Thank you MuckRock for this contribution.
    """

    max_pagination_depth = 100

    def paginate_queryset(self, queryset, request, view=None):
        """
        Paginate a queryset if required, either returning a
        page object, or `None` if pagination is not configured for this view.
        """
        page_size = self.get_page_size(request)
        if not page_size:
            return None

        paginator = self.django_paginator_class(queryset, page_size)
        page_number = self.get_page_number(request, paginator)

        try:
            page_number = int(page_number)
        except (TypeError, ValueError):
            msg = "Invalid page: That page number is not an integer"
            raise NotFound(msg)

        if page_number > self.max_pagination_depth:
            msg = "Invalid page: Deep API pagination is not allowed. Please review API documentation."
            raise NotFound(msg)

        try:
            self.page = paginator.page(page_number)
        except InvalidPage as exc:
            msg = self.invalid_page_message.format(
                page_number=page_number, message=str(exc)
            )
            raise NotFound(msg)

        if paginator.num_pages > 1 and self.template is not None:
            # The browsable API should display pagination controls.
            self.display_page_controls = True

        self.request = request
        return list(self.page)


class TinyAdjustablePagination(ShallowOnlyPageNumberPagination):
    page_size = 5
    page_size_query_param = "page_size"
    max_page_size = 20


class MediumAdjustablePagination(ShallowOnlyPageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"


class BigPagination(ShallowOnlyPageNumberPagination):
    page_size = 300


class ESCursorPagination(BasePagination):
    """Custom pagination class to handle ES cursor pagination, based in the ES
    search_after param.
    """

    request = None
    es_list_instance = None
    results_count_exact = None
    results_count_approximate = None
    child_results_count = None
    results_in_page = None
    base_url = None
    cursor = None
    search_type = None
    cursor_query_param = "cursor"
    invalid_cursor_message = "Invalid cursor"

    def paginate_queryset(
        self, es_list_instance: CursorESList, request: Request, view=None
    ) -> list[defaultdict]:
        """Paginate the Elasticsearch query and retrieve the results."""

        self.base_url = request.build_absolute_uri()
        self.request = request
        self.es_list_instance = es_list_instance
        self.search_type = self.es_list_instance.clean_data["type"]
        self.cursor = self.decode_cursor(request)
        self.es_list_instance.set_pagination(
            self.cursor, settings.SEARCH_API_PAGE_SIZE
        )
        results, main_hits, cardinality_count, child_cardinality_count = (
            self.es_list_instance.get_paginated_results()
        )
        self.results_in_page = len(results)
        self.results_count_approximate = cardinality_count
        self.results_count_exact = main_hits
        self.child_results_count = child_cardinality_count
        return results

    def get_paginated_response(self, data):
        """Generate a custom paginated response using the data provided."""

        base_response = {
            "count": self.get_results_count(),
        }
        remaining_fields = {
            "next": self.get_next_link(),
            "previous": self.get_previous_link(),
            "results": data,
        }

        if self.search_type == SEARCH_TYPES.RECAP:
            # Include the document_count for the "r" search type.
            base_response.update(
                {"document_count": self.get_child_results_count()}
            )
        base_response.update(remaining_fields)
        return Response(base_response)

    def get_next_link(self) -> str | None:
        """Constructs the URL for the next page based on the current page's
        last item.
        """
        search_after_sort_key = (
            self.es_list_instance.get_search_after_sort_key()
        )
        if not self.has_next():
            return None

        cursor = ESCursor(
            search_after=search_after_sort_key,
            reverse=False,
            search_type=self.search_type,
        )
        return self.encode_cursor(cursor)

    def get_previous_link(self) -> str | None:
        """Constructs the URL for the next page based on the current page's
        last item.
        """
        reverse_search_after_sort_key = (
            self.es_list_instance.get_reverse_search_after_sort_key()
        )
        if not self.has_prev():
            return None

        cursor = ESCursor(
            search_after=reverse_search_after_sort_key,
            reverse=True,
            search_type=self.search_type,
        )
        return self.encode_cursor(cursor)

    def decode_cursor(self, request: Request) -> ESCursor | None:
        """Given a request with a cursor, return a `ESCursor` instance."""

        encoded = request.query_params.get(self.cursor_query_param)
        if encoded is None:
            return None
        try:
            querystring = b64decode(encoded.encode("ascii")).decode("ascii")
            tokens = parse_qs(querystring, keep_blank_values=True)
            search_after = tokens.get("s", None)
            reverse = tokens.get("r", ["0"])[0]
            reverse = bool(int(reverse))
            search_type = tokens.get("t", [None])[0]
        except (TypeError, ValueError):
            raise NotFound(self.invalid_cursor_message)

        if search_type != self.search_type:
            # If the search_type has changed in the request, but the search type
            # in the cursor doesn't match, raise an invalid cursor error to
            # avoid pagination inconsistencies.
            raise NotFound(self.invalid_cursor_message)
        return ESCursor(
            search_after=search_after, reverse=reverse, search_type=search_type
        )

    def encode_cursor(self, cursor: ESCursor) -> str:
        """Given a ESCursor instance, return an url with encoded cursor."""
        tokens = {}
        if cursor.search_after != 0:
            tokens["s"] = cursor.search_after
        if cursor.reverse:
            tokens["r"] = "1"
        if cursor.search_type:
            tokens["t"] = self.search_type

        querystring = urlencode(tokens, doseq=True)
        encoded = b64encode(querystring.encode("ascii")).decode("ascii")
        return replace_query_param(
            self.base_url, self.cursor_query_param, encoded
        )

    def get_results_count(self) -> int:
        """Provides the count of results based on either the main query count
         hits or the cardinality query, if the results hits exceed the
         ELASTICSEARCH_MAX_RESULT_COUNT.

        :return: An integer representing the number of results matching the query.
        """

        approximate_count = (
            self.results_count_approximate.aggregations.unique_documents.value
        )
        return (
            self.results_count_exact
            if self.results_count_exact
            < settings.ELASTICSEARCH_MAX_RESULT_COUNT
            else approximate_count
        )

    def get_child_results_count(self) -> int:
        """Provides the count of child documents based on a cardinality query.
        :return: An integer representing the number of child documents
        matching the query.
        """

        return self.child_results_count.aggregations.unique_documents.value

    def has_next(self) -> bool:
        """Determines if there is a next page based on the search_after key
        and results count.
        """
        if not self.cursor or not self.cursor.reverse:
            # If this is the first page or if going forward, check if the
            # number of results on the page exceeds the page size.
            # This indicates that there is a next page.
            return self.results_in_page > settings.SEARCH_API_PAGE_SIZE

        # If going backward, it indicates that there was a next page.
        return True

    def has_prev(self) -> bool:
        """Determines if there is a next page based on the search_after key
        and results count.
        """
        # Check if it's the first page or if there are no results on the page.
        if self.cursor is None:
            return False

        if self.cursor.reverse:
            # If going backwards, check if the results contains more items than
            # the page size. This indicates that there is a previous page to
            # display.
            return self.results_in_page > settings.SEARCH_API_PAGE_SIZE

        # If going forward, it indicates that there was a previous page.
        return True
