import datetime

from django.db.models import Prefetch
from django.http import QueryDict
from django.utils.timezone import now

from cl.alerts.models import Alert, ParentAlert, UserRateAlert
from cl.alerts.send_alerts import (
    merge_highlights_into_result,
    send_search_alert_and_webhooks,
)
from cl.alerts.utils import InvalidDateError
from cl.lib.command_utils import VerboseCommand, logger
from cl.search.constants import ALERTS_HL_TAG
from cl.search.models import SEARCH_TYPES
from cl.stats.utils import tally_stat


def json_date_parser(dct):
    for key, value in dct.items():
        if isinstance(value, str):
            try:
                dct[key] = datetime.datetime.fromisoformat(value)
            except ValueError:
                pass
    return dct


def query_and_send_alerts_by_rate(rate: str) -> None:
    """Query and send alerts per user.

    :param rate: The alert rate to send Alerts.
    :return: None
    """

    alerts_sent_count = 0
    now_time = now()
    alerts_to_update = []
    rate_users = (
        UserRateAlert.objects.filter(rate=rate)
        .select_related("user")
        .prefetch_related(
            Prefetch(
                "parent_alerts",
                queryset=ParentAlert.objects.select_related(
                    "alert"
                ).prefetch_related("scheduled_alerts"),
            )
        )
    )

    for rate_user in rate_users.iterator():
        hits = []
        for parent_alert in rate_user.parent_alerts.all():
            results = parent_alert.scheduled_alerts.all()
            qd = QueryDict(parent_alert.alert.query.encode(), mutable=True)
            search_type = qd.get("type", SEARCH_TYPES.OPINION)
            documents = []

            for result in results:
                document_content = json_date_parser(result.document_content)
                if result.highlighted_fields:
                    merge_highlights_into_result(
                        result.highlighted_fields,
                        document_content,
                        ALERTS_HL_TAG,
                    )
                documents.append(document_content)
            alerts_to_update.append(parent_alert.alert)
            hits.append(
                (
                    parent_alert.alert,
                    search_type,
                    documents,
                    len(documents),
                )
            )
        send_search_alert_and_webhooks(rate_user.user, hits)
        if rate_user.parent_alerts.exists():
            alerts_sent_count += 1

    # Update Alert's date_last_hit in bulk.
    Alert.objects.filter(
        id__in=[alert.id for alert in alerts_to_update]
    ).update(date_last_hit=now_time)

    # Remove stored alerts sent, all the related objects will be deleted
    # in cascade.
    rate_users.delete()

    tally_stat(f"alerts.sent.{rate}", inc=alerts_sent_count)
    logger.info(f"Sent {alerts_sent_count} {rate} email alerts.")


def send_scheduled_alerts(rate: str) -> None:
    if rate == Alert.DAILY:
        query_and_send_alerts_by_rate(Alert.DAILY)
    elif rate == Alert.WEEKLY:
        query_and_send_alerts_by_rate(Alert.WEEKLY)
    elif rate == Alert.MONTHLY:
        if datetime.date.today().day > 28:
            raise InvalidDateError(
                "Monthly alerts cannot be run on the 29th, 30th or 31st."
            )
        query_and_send_alerts_by_rate(Alert.MONTHLY)


class Command(VerboseCommand):
    help = "Send scheduled Search Alerts."

    def add_arguments(self, parser):
        parser.add_argument(
            "--rate",
            required=True,
            choices=Alert.ALL_FREQUENCIES,
            help=f"The rate to send emails ({', '.join(Alert.ALL_FREQUENCIES)})",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        send_scheduled_alerts(options["rate"])
