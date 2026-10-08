from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from django.db.models import QuerySet
from rest_framework.serializers import ModelSerializer

from cl.corpus_importer.api_serializers import (
    DocketEntrySerializer,
    SCOTUSDocketEntrySerializer,
)
from cl.search.models import Docket, DocketEntry, SCOTUSDocketEntry


@dataclass(frozen=True)
class DocketAlertSource:
    """Describes how one "flavor" of docket resolves the entries a docket
    alert should notify about, which templates render its email, and which
    serializer builds its webhook payload.
    RECAP/PACER is the default; SCOTUS is the first override.

    ``entries_by_pk`` resolves a precise list of entry pks into a queryset --
    used for RECAP's recap.email re-notify case, where the caller already
    knows exactly which (already-seen) entry it's re-announcing.

    ``entries_since`` resolves entries created at or after a timestamp --
    the normal way a docket alert finds "what's new" for any source.

    ``email_txt_template``/``email_html_template`` name the templates
    make_alert_messages renders for this source.

    ``webhook_serializer`` is the ModelSerializer
    send_docket_alert_webhook_events uses for this source's entries.
    Callers must look up entries through this source rather than
    DocketEntry, because entry pks are not unique across tables.
    """

    entries_by_pk: Callable[[list[int]], QuerySet]
    entries_since: Callable[[Docket, datetime], QuerySet]
    email_txt_template: str
    email_html_template: str
    webhook_serializer: type[ModelSerializer]


# RECAP


def _recap_entries_by_pk(des_pks: list[int]) -> QuerySet:
    """Return the DocketEntry rows matching the given pks."""
    return DocketEntry.objects.filter(pk__in=des_pks).prefetch_related(
        "recap_documents"
    )


def _recap_entries_since(docket: Docket, since: datetime) -> QuerySet:
    """Return the docket's entries created at or after `since`."""
    return DocketEntry.objects.filter(date_created__gte=since, docket=docket)


RECAP_ALERT_SOURCE = DocketAlertSource(
    entries_by_pk=_recap_entries_by_pk,
    entries_since=_recap_entries_since,
    email_txt_template="docket_alert_email.txt",
    email_html_template="docket_alert_email.html",
    webhook_serializer=DocketEntrySerializer,
)


# SCOTUS


def _scotus_entries_by_pk(des_pks: list[int]) -> QuerySet:
    """Return the SCOTUSDocketEntry rows matching the given pks."""
    return SCOTUSDocketEntry.objects.filter(pk__in=des_pks).prefetch_related(
        "scotusdocument_set"
    )


def _scotus_entries_since(docket: Docket, since: datetime) -> QuerySet:
    """Return the docket's SCOTUSDocketEntry rows created at or after
    `since`."""
    return SCOTUSDocketEntry.objects.filter(
        date_created__gte=since, docket=docket
    )


SCOTUS_ALERT_SOURCE = DocketAlertSource(
    entries_by_pk=_scotus_entries_by_pk,
    entries_since=_scotus_entries_since,
    email_txt_template="docket_alert_email_scotus.txt",
    email_html_template="docket_alert_email_scotus.html",
    webhook_serializer=SCOTUSDocketEntrySerializer,
)


_ALERT_SOURCES_BY_COURT_ID: dict[str, DocketAlertSource] = {
    "scotus": SCOTUS_ALERT_SOURCE,
}
