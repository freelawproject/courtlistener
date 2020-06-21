# coding=utf-8
from argparse import RawTextHelpFormatter

from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives
from django.template import loader
from django.utils.timezone import now

from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.date_time import dt_as_local_date


class OldAlertReport:
    def __init__(self):
        self.ninety_ago = []
        self.one_eighty_ago = []
        self.disabled_dockets = []

    def total_count(self):
        return (
            len(self.ninety_ago)
            + len(self.one_eighty_ago)
            + len(self.disabled_dockets)
        )


def build_user_report(user, delete=False):
    """Figure out which alerts are old or too old; delete very old ones

    :param user: A user that has alerts
    :param delete: Whether to nuke really old alerts
    :return A dict indicating the counts of old alerts.
    """
    report = OldAlertReport()
    alerts = user.docket_alerts.exclude(
        docket__date_terminated=None
    ).select_related("docket")
    for alert in alerts:
        # Use the more recent of the date the alert was created, the date it
        # was last triggered, or the date_terminated of the docket
        threshold_date = max(
            alert.docket.date_terminated, dt_as_local_date(alert.date_created)
        )
        if alert.date_last_hit is not None:
            threshold_date = max(
                threshold_date, dt_as_local_date(alert.date_last_hit)
            )
        days_since_last_touch = (dt_as_local_date(now()) - threshold_date).days
        if delete:
            if days_since_last_touch >= 187:
                report.disabled_dockets.append(alert.docket)
                alert.delete()
            elif 180 <= days_since_last_touch <= 186:
                report.one_eighty_ago.append(alert.docket)
            elif 90 <= days_since_last_touch <= 96:
                report.ninety_ago.append(alert.docket)
        else:
            # Useful for first run, when ew *only* want to warn and not to
            # disable.
            if days_since_last_touch >= 180:
                report.one_eighty_ago.append(alert.docket)
            elif 90 <= days_since_last_touch <= 96:
                report.ninety_ago.append(alert.docket)

    return report


def send_old_alert_warning(user, report):
    """Send alerts for old alerts

    :param user: The user with terminated dockets
    :param report: A dict containing information about old alerts
    :return None
    """
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
""".decode(
        "utf-8"
    )

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
            docket_alerts__docket__date_terminated__isnull=False
        ).distinct()
        logger.info(
            "%s users have terminated alerts to check.", len(users_with_alerts)
        )
        emails_sent = 0
        alerts_deleted = 0
        for user in users_with_alerts:
            report = build_user_report(
                user, delete=options["delete_old_alerts"]
            )
            alerts_deleted += len(report.disabled_dockets)
            count = report.total_count()
            if options["send_alerts"] and count > 0:
                emails_sent += 1
                send_old_alert_warning(user, report)

        logger.info(
            "%s alerts deleted (or skipped if arg not provided).",
            alerts_deleted,
        )
        logger.info("%s notification emails sent.", emails_sent)
