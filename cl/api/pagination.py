from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from django.conf import settings
from django.core.paginator import InvalidPage
from rest_framework.exceptions import NotFound
from rest_framework.pagination import BasePagination, PageNumberPagination
from rest_framework.response import Response


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

    def __init__(self):
        self.page_size = settings.SEARCH_API_PAGE_SIZE
        self.request = None
        self.search_after = None
        self.es_list_instance = None
        self.results_count = None
        self.results_in_page = None

    def paginate_queryset(self, es_list_instance, request, view=None):
        """Paginate the Elasticsearch query and retrieve the results."""

        self.request = request
        self.search_after = self.decode_cursor(
            request.query_params.get("page", None)
        )
        self.es_list_instance = es_list_instance
        self.es_list_instance.set_pagination(self.search_after, self.page_size)
        results = self.es_list_instance.get_paginated_results()
        self.results_in_page = len(results)
        self.results_count = results.hits.total.value
        return results

    def get_paginated_response(self, data):
        """Generate a custom paginated response using the data provided."""
        return Response(
            {
                "count": self.get_results_count(),
                "next": self.get_next_link(),
                "results": data,
            }
        )

    def get_next_link(self):
        """Constructs the URL for the next page based on the current page's
        last item.
        """
        search_after_sort_key = (
            self.es_list_instance.get_search_after_sort_key()
        )
        if not self.has_next(search_after_sort_key):
            return None

        encoded_cursor = "_".join(map(str, search_after_sort_key))
        parsed_url = urlparse(self.request.build_absolute_uri())
        query = parse_qs(parsed_url.query)
        query["page"] = [encoded_cursor]
        url_parts = list(parsed_url)
        url_parts[4] = urlencode(query, doseq=True)
        return urlunparse(url_parts)

    def decode_cursor(self, cursor):
        """Decodes the cursor string into a list."""

        return cursor.split("_") if cursor else None

    def get_results_count(self):
        """Provides a structured count of results based on settings.

        :return: A dictionary containing "exact" count and whether there are
        "more" or equal results than ELASTICSEARCH_MAX_RESULT_COUNT.
        """
        return {
            "exact": (
                self.results_count
                if self.results_count
                <= settings.ELASTICSEARCH_MAX_RESULT_COUNT
                else settings.ELASTICSEARCH_MAX_RESULT_COUNT
            ),
            "more": self.results_count
            > settings.ELASTICSEARCH_MAX_RESULT_COUNT,
        }

    def has_next(self, search_after_sort_key):
        """Determines if there is a next page based on the search_after key
        and results count.
        """
        if search_after_sort_key is None:
            return False
        if self.results_in_page < self.page_size:
            return False
        return True
