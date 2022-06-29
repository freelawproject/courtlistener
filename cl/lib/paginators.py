from django.core.paginator import Paginator
from django.utils.functional import cached_property


class ESPaginator(Paginator):
    """
    Paginator for Elasticsearch hits(results), elasticsearch already provides total
    count from query
    """

    def __init__(self, *args, **kwargs):
        super(ESPaginator, self).__init__(*args, **kwargs)
        self._count = (
            self.object_list.hits.total.value
            if hasattr(self.object_list, "hits")
            else 0
        )

    @cached_property
    def execution_time(self):
        """Return query execution time"""
        return (
            self.object_list.took if hasattr(self.object_list, "took") else 0
        )
