# coding=utf-8
from argparse import RawTextHelpFormatter

from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives
from django.template import loader
from django.utils.timezone import now

from cl.lib.command_utils import VerboseCommand


def build_user_report(user):
    """Figure out which alerts are old or too old; delete very old ones

    :param user: A user that has alerts
    :return A dict indicating the counts of old alerts.
    """
    report = {
        "ninety_ago": [],
        "one_eighty_ago": [],
        "disabled_dockets": [],
    }
    alerts = user.docket_alerts.exclude(
        docket__date_terminated=None
    ).select_related("docket")
    for alert in alerts:
        date_terminated = alert.docket.date_terminated
        # Use the more recent of the date the alert was created, the date it
        # was last triggered, or the date_terminated of the docket
        threshold_date = max(date_terminated, alert.date_created.date())
        if alert.date_last_hit is not None:
            threshold_date = max(threshold_date, alert.date_last_hit.date())
        days_since_last_touch = (now().date() - threshold_date).days
        if days_since_last_touch >= 187:
            report["disabled_dockets"].append(alert.docket)
            alert.delete()
        elif 180 <= days_since_last_touch <= 186:
            report["one_eighty_ago"].append(alert.docket)
        elif 90 <= days_since_last_touch <= 96:
            report["ninety_ago"].append(alert.docket)

    return report


def send_old_alert_warning(user, report_data):
    """Send alerts for old alerts

    :param user: The user with terminated dockets
    :param report_data: A dict containing information about old alerts
    :return None
    """
    count = 0
    for value in report_data.values():
        count += len(value)
    if count == 0:
        return
    subject_template = loader.get_template("emails/old_email_subject.txt")
    subject = subject_template.render({"count": count}).strip()
    txt = loader.get_template("emails/old_alert_email.txt").render(report_data)
    html = loader.get_template("emails/old_alert_email.html").render(
        report_data
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

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)

        # Needs to be user-oriented so that we only send one email per person.
        users_with_alerts = User.objects.exclude(
            docket_alerts__docket__date_terminated=None
        )

        for user in users_with_alerts:
            report_data = build_user_report(user)
            send_old_alert_warning(user, report_data)
