from argparse import RawTextHelpFormatter

from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives
from django.template import loader
from django.utils.timezone import now

from cl.alerts.models import DocketAlert
from cl.alerts.utils import DocketAlertReportObject, OldAlertReport
from cl.api.models import WebhookEventType
from cl.api.webhooks import send_old_alerts_webhook_event
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.date_time import dt_as_local_date


def build_user_report(user, delete=False):
    """Figure out which alerts are old or too old; disable very old ones based
    on date_modified since this field is updated when the alert_type field is
    toggled

    :param user: A user that has alerts
    :param delete: Whether to disable really old alerts
    :return A dict indicating the counts of old alerts.
    """

    report = OldAlertReport()
    alerts = (
        user.docket_alerts.filter(alert_type=DocketAlert.SUBSCRIPTION)
        .exclude(docket__date_terminated=None)
        .select_related("docket")
    )

    for alert in alerts:
        # Use the most recent of several fields that might be related to the
        # docket or the alert.

        threshold_date = max(
            alert.docket.date_terminated, dt_as_local_date(alert.date_modified)
        )

        if alert.date_last_hit is not None:
            threshold_date = max(
                threshold_date, dt_as_local_date(alert.date_last_hit)
            )
        if alert.docket.date_last_filing:
            threshold_date = max(threshold_date, alert.docket.date_last_filing)

        days_since_last_touch = (dt_as_local_date(now()) - threshold_date).days
        if delete:
            if days_since_last_touch >= 187:
                report.disabled_alerts.append(
                    DocketAlertReportObject(alert, alert.docket)
                )
                # Toggle docket alert to unsubscription type
                alert.alert_type = DocketAlert.UNSUBSCRIPTION
                alert.save()
            elif 180 <= days_since_last_touch <= 186:
                report.very_old_alerts.append(
                    DocketAlertReportObject(alert, alert.docket)
                )
            elif 90 <= days_since_last_touch <= 96:
                report.old_alerts.append(
                    DocketAlertReportObject(alert, alert.docket)
                )
        else:
            # Useful for first run, when ew *only* want to warn and not to
            # disable.
            if days_since_last_touch >= 180:
                report.very_old_alerts.append(
                    DocketAlertReportObject(alert, alert.docket)
                )
            elif 90 <= days_since_last_touch <= 96:
                report.old_alerts.append(
                    DocketAlertReportObject(alert, alert.docket)
                )

    return report


def send_old_alert_warning_email_and_webhook(user, report) -> int:
    """Send alerts emails and webhooks for old alerts

    :param user: The user with terminated dockets
    :param report: A dict containing information about old alerts
    :return The number of webhook events sent
    """

    user_webhooks = user.webhooks.filter(
        event_type=WebhookEventType.OLD_DOCKET_ALERTS_REPORT, enabled=True
    )
    webhook_count = 0
    if report.very_old_alerts or report.disabled_alerts:
        for user_webhook in user_webhooks:
            send_old_alerts_webhook_event(user_webhook, report)
            webhook_count += 1

    count = report.total_count()
    subject_template = loader.get_template("emails/old_email_subject.txt")
    subject = subject_template.render({"count": count}).strip()
    txt = loader.get_template("emails/old_alert_email.txt").render(
        {"report_data": report},
    )
    html = loader.get_template("emails/old_alert_email.html").render(
        {"report_data": report},
    )
    msg = EmailMultiAlternatives(
        subject, txt, settings.DEFAULT_ALERTS_EMAIL, [user.email]
    )
    msg.attach_alternative(html, "text/html")
    msg.send(fail_silently=False)
    return webhook_count


class Command(VerboseCommand):
    help = """Check for old docket alerts and email or disable them.

Alerts are sent weekly, therefore we have to capture things in date ranges.
This prevents us from sending too many notifications or not enough.

The schedule is thus:

     Day 0 ─┬─ Item is terminated
            │
            │
   T+90-96 ─┼─ Item terminated about 90 days ago,
            │  did you want to disable it?
            │
 T+180-186 ─┼─ Item terminated about 180 days ago, alerts will be disabled
            │  in one week if you do not disable and re-enable your alert.
            │
   T+187-∞ ─┴─ Item terminated more than 180 days ago and
               alert is disabled.
"""

    def create_parser(self, *args, **kwargs):
        parser = super(Command, self).create_parser(*args, **kwargs)
        parser.formatter_class = RawTextHelpFormatter
        return parser

    def add_arguments(self, parser):
        parser.add_argument(
            "--delete-old-alerts",
            action="store_true",
            default=False,
            help="Make sure to use this flag to delete old alerts",
        )
        parser.add_argument(
            "--send-alerts",
            action="store_true",
            default=False,
            help="Make sure to use this flag to send emails",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)

        # Needs to be user-oriented so that we only send one email per person.
        users_with_alerts = User.objects.filter(
            docket_alerts__docket__date_terminated__isnull=False,
            docket_alerts__alert_type=DocketAlert.SUBSCRIPTION,
        ).distinct()
        logger.info(
            "%s users have terminated alerts to check.", len(users_with_alerts)
        )
        emails_sent = 0
        alerts_deleted = 0
        webhooks_sent = 0
        for user in users_with_alerts:
            report = build_user_report(
                user, delete=options["delete_old_alerts"]
            )
            alerts_deleted += len(report.disabled_alerts)
            count = report.total_count()
            if options["send_alerts"] and count > 0:
                emails_sent += 1
                webhooks_count = send_old_alert_warning_email_and_webhook(
                    user, report
                )
                webhooks_sent += webhooks_count

        logger.info(
            f"{alerts_deleted} alerts deleted (or skipped if arg not provided)."
        )
        logger.info(f"{emails_sent} notification emails sent.")
        logger.info(
            f"{webhooks_sent} webhooks sent.",
        )
