import datetime
from base64 import b64decode, b64encode
from collections import defaultdict
from urllib.parse import parse_qs, urlencode

from django.conf import settings
from django.core.paginator import InvalidPage
from django.db.models import QuerySet
from rest_framework.exceptions import NotFound
from rest_framework.pagination import (
    BasePagination,
    CursorPagination,
    PageNumberPagination,
)
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.utils.urls import replace_query_param

from cl.search.api_utils import CursorESList
from cl.search.models import SEARCH_TYPES
from cl.search.types import ESCursor


class VersionBasedPagination(PageNumberPagination):
    """The base paginator for handling V3 and V4 DB endpoints.
    This supports CursorPagination for V4 endpoints when sorting by "id" or
    "date_created". It uses PageNumberPagination for V3 endpoints and for V4
    endpoints when sorting by keys that don't support CursorPagination.
    """

    max_pagination_depth = 100
    version = "v3"
    cursor_query_param = "cursor"
    invalid_cursor_message = "Invalid cursor"
    compatible_sorting = {
        "id": "int",
        "-id": "int",
        "date_created": "date",
        "-date_created": "date",
        "date_modified": "date",
        "-date_modified": "date",
    }
    ordering = ""
    other_cursor_ordering_keys = []

    def __init__(self):
        super().__init__()
        self.cursor_paginator = CursorPagination()
        self.cursor_paginator.page_size = self.page_size

    def do_v4_cursor_pagination(self):
        """Determine if v4 cursor pagination should be applied.

        :return: A two tuple containing:
        - A boolean indicating if cursor pagination should be applied.
        - The requested ordering key if applicable.
        """

        all_cursor_ordering_keys = []
        requested_ordering = self.request.query_params.get(
            "order_by", self.ordering
        )
        all_cursor_ordering_keys.extend(self.other_cursor_ordering_keys)
        all_cursor_ordering_keys.append(self.ordering)
        return (
            all(
                [
                    self.version == "v4",
                    requested_ordering,
                    requested_ordering in all_cursor_ordering_keys,
                ]
            ),
            requested_ordering,
        )

    def paginate_queryset(self, queryset, request, view=None):
        """
        Paginate a queryset if required, either returning a
        page object, or `None` if pagination is not configured for this view.
        """

        if hasattr(view, "ordering"):
            self.ordering = view.ordering
        if hasattr(view, "other_cursor_ordering_keys"):
            self.other_cursor_ordering_keys = view.other_cursor_ordering_keys

        self.version = request.version
        self.request = request
        do_cursor_pagination, requested_ordering = (
            self.do_v4_cursor_pagination()
        )
        if do_cursor_pagination:
            # Handle the queryset using CursorPagination
            return handle_database_cursor_pagination(
                self, request, requested_ordering, queryset, view
            )

        # Handle the queryset using PageNumberPagination
        return self.handle_shallow_only_page_number_pagination(
            request, queryset
        )

    def get_paginated_response(self, data):
        do_cursor_pagination, _ = self.do_v4_cursor_pagination()
        if do_cursor_pagination:
            # Get paginated response for CursorPagination
            return self.cursor_paginator.get_paginated_response(data)

        # Get paginated response for PageNumberPagination
        return super().get_paginated_response(data)

    def handle_shallow_only_page_number_pagination(
        self, request: Request, queryset: QuerySet
    ) -> list | None:
        """A paginator that blocks deep pagination

         Thank you MuckRock for this contribution.

        :param self: The VersionBasedPagination instance.
        :param request: The DRF Request object.
        :param queryset: The Django QuerySet to be paginated.
        :return: A paginated list of query results.
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


def determine_cursor_position_type(position: str) -> str:
    """Determine the type of given string.

    :param position: The input cursor to classify.
    :return: A string indicating the type of the input
    ('int', 'date', or 'unknown').
    """
    # Check if it's an integer.
    if position.isdigit():
        return "int"

    # Try to parse as date
    try:
        datetime.datetime.fromisoformat(position)
        return "date"
    except ValueError:
        pass

    return "unknown"


def handle_database_cursor_pagination(
    self: VersionBasedPagination,
    request: Request,
    requested_ordering: str,
    queryset: QuerySet,
    view,
) -> list | None:
    """Handle cursor pagination for database queries based on the request and
     ordering.

    :param self: The VersionBasedPagination instance.
    :param request: The DRF Request object.
    :param requested_ordering: The field by which the queryset should be ordered.
    :param queryset: The Django QuerySet to be paginated.
    :param view: The view instance from which this method is called.
    :return: A paginated list of query results.
    """

    if self.cursor_query_param in request.query_params:
        cursor = self.cursor_paginator.decode_cursor(request)
        cursor_position = cursor and cursor.position
        position_type = determine_cursor_position_type(str(cursor_position))
        valid_sorting = self.compatible_sorting[requested_ordering]
        if valid_sorting != position_type:
            raise NotFound(self.invalid_cursor_message)

    self.cursor_paginator.ordering = requested_ordering
    return self.cursor_paginator.paginate_queryset(queryset, request, view)


class TinyAdjustablePagination(VersionBasedPagination):
    page_size = 5
    page_size_query_param = "page_size"
    max_page_size = 20


class MediumAdjustablePagination(VersionBasedPagination):
    page_size = 50
    page_size_query_param = "page_size"


class BigPagination(VersionBasedPagination):
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
    request_date = None

    def initialize_context_from_request(
        self, request, search_type
    ) -> datetime.date:
        self.base_url = request.build_absolute_uri()
        self.request = request
        self.search_type = search_type
        self.cursor = self.decode_cursor(request)

        # Set the request date from the cursor or provide an initial one if
        # this is the first page request.
        self.request_date = (
            self.cursor.request_date
            if self.cursor
            else datetime.datetime.now().date()
        )
        return self.request_date

    def paginate_queryset(
        self, es_list_instance: CursorESList, request: Request, view=None
    ) -> list[defaultdict]:
        """Paginate the Elasticsearch query and retrieve the results."""

        self.es_list_instance = es_list_instance
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
            request_date=self.request_date,
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
            request_date=self.request_date,
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
            reverse = bool(int(tokens.get("r", ["0"])[0]))
            search_type = tokens.get("t", [None])[0]
            request_date = tokens.get("d", [None])[0]
        except (TypeError, ValueError):
            raise NotFound(self.invalid_cursor_message)

        if search_type != self.search_type:
            # If the search_type has changed in the request, but the search type
            # in the cursor doesn't match, raise an invalid cursor error to
            # avoid pagination inconsistencies.
            raise NotFound(self.invalid_cursor_message)

        request_date = (
            datetime.date.fromisoformat(request_date) if request_date else None
        )
        self.cursor = ESCursor(
            search_after=search_after,
            reverse=reverse,
            search_type=search_type,
            request_date=request_date,
        )
        return self.cursor

    def encode_cursor(self, cursor: ESCursor) -> str:
        """Given a ESCursor instance, return an url with encoded cursor."""
        tokens = {}
        if cursor.search_after != 0:
            tokens["s"] = cursor.search_after
        if cursor.reverse:
            tokens["r"] = "1"
        if cursor.search_type:
            tokens["t"] = self.search_type
        if cursor.request_date:
            tokens["d"] = cursor.request_date

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
