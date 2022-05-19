from django.core.paginator import InvalidPage
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination


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
