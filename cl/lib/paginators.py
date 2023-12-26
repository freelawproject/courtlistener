from django.core.paginator import Paginator
from django.utils.functional import cached_property


class ESPaginator(Paginator):
    """
    Paginator for Elasticsearch hits(results).
    """

    def __init__(self, total_query_results: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._count = total_query_results

    @cached_property
    def count(self) -> int:
        """Get the global number of objects, across all pages."""
        return self._count

    def page(self, number):
        number = self.validate_number(number)
        return self._get_page(self.object_list, number, self)
