from dataclasses import dataclass

from cl.alerts.models import DocketAlert
from cl.search.models import Docket


@dataclass
class DocketAlertReportObject:
    da_alert: DocketAlert
    docket: Docket


class OldAlertReport:
    def __init__(self):
        self.old_alerts = []
        self.very_old_alerts = []
        self.disabled_alerts = []

    @property
    def old_dockets(self):
        return [obj.docket for obj in self.old_alerts]

    @property
    def very_old_dockets(self):
        return [obj.docket for obj in self.very_old_alerts]

    @property
    def disabled_dockets(self):
        return [obj.docket for obj in self.disabled_alerts]

    def total_count(self):
        return (
            len(self.old_alerts)
            + len(self.very_old_alerts)
            + len(self.disabled_alerts)
        )


class InvalidDateError(Exception):
    pass
