from cl.alerts.models import Alert, DocketAlert
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


class DocketAlertFilter(NoEmptyFilterSet):
    class Meta:
        model = DocketAlert
        fields = {
            "id": ["exact"],
            "alert_type": ["exact"],
            "docket": ["exact"],
        }
