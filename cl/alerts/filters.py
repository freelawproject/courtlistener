from cl.alerts.models import Alert
from cl.api.utils import BASIC_TEXT_LOOKUPS, NoEmptyFilterSet


class SearchAlertFilter(NoEmptyFilterSet):
    class Meta:
        model = Alert
        fields = {
            "id": ["exact"],
            "name": BASIC_TEXT_LOOKUPS,
            "query": BASIC_TEXT_LOOKUPS,
            "rate": ["exact"],
        }
