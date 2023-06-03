from django.core.paginator import Paginator
from django.utils.functional import cached_property


class ESPaginator(Paginator):
    """
    Paginator for Elasticsearch hits(results).
    """

    def __init__(self, *args, **kwargs):
        super(ESPaginator, self).__init__(*args, **kwargs)
        self._count = (
            self.object_list.hits.total.value
            if hasattr(self.object_list, "hits")
            else len(self.object_list)
        )

    @cached_property
    def count(self):
        """Set the global number of objects, across all pages."""
        return self._count

    def page(self, number):
        number = self.validate_number(number)
        return self._get_page(self.object_list, number, self)
