"""REST API filters for search and docket alerts."""

from cl.alerts.models import Alert, DocketAlert
from cl.api.utils import BASIC_TEXT_LOOKUPS, NoEmptyFilterSet


class SearchAlertFilter(NoEmptyFilterSet):
    """Filter search alerts by ID, name, query, and rate."""

    class Meta:
        model = Alert
        fields = {
            "id": ["exact"],
            "name": BASIC_TEXT_LOOKUPS,
            "query": BASIC_TEXT_LOOKUPS,
            "rate": ["exact"],
        }


class DocketAlertFilter(NoEmptyFilterSet):
    """Filter docket alerts by ID, alert type, and docket."""

    class Meta:
        model = DocketAlert
        fields = {
            "id": ["exact"],
            "alert_type": ["exact"],
            "docket": ["exact"],
        }
