from dataclasses import dataclass

from django.conf import settings

from cl.alerts.models import Alert, DocketAlert
from cl.search.documents import AudioPercolator
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


def index_alert_document(alert: Alert, es_document=AudioPercolator) -> None:
    """Helper method to prepare and index an Alert object into Elasticsearch.

    :param alert: The Alert instance to be indexed.
    :param es_document: The Elasticsearch document percolator used for indexing
    the Alert instance.
    :return: None
    """
    document = es_document()
    doc = document.prepare(alert)
    es_document(meta={"id": alert.pk}, **doc).save(
        skip_empty=True, refresh=settings.ELASTICSEARCH_DSL_AUTO_REFRESH
    )
