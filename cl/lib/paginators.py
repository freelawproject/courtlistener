from django.core.paginator import Paginator
from django.utils.functional import cached_property


class ESPaginator(Paginator):
    """
    Paginator for Elasticsearch hits(results).
    """

    def __init__(self, total_query_results: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._count = total_query_results
        self._aggregations = (
            self.object_list.aggregations
            if hasattr(self.object_list, "aggregations")
            else {}
        )

    @cached_property
    def count(self) -> int:
        """Get the global number of objects, across all pages."""
        return self._count

    @cached_property
    def aggregations(self):
        """Set the aggregation object, across all pages."""
        return self._aggregations

    def page(self, number):
        number = self.validate_number(number)
        return self._get_page(self.object_list, number, self)
