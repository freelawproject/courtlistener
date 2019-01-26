import datetime
import time

from django.conf import settings
from django.core.mail import send_mail
from django.template import loader
from django.utils.timezone import now
from juriscraper.pacer import CaseQueryAdvancedBankruptcy, PacerSession

from cl.lib.command_utils import VerboseCommand


def send_emails(report, recipients):
    subject = 'The PG&E Bankruptcy is Posted'
    template = loader.get_template('pacer_alert_email.txt')
    context = {'report': report}
    send_mail(
        subject=subject,
        message=template.render(context),
        from_email=settings.DEFAULT_ALERTS_EMAIL,
        recipient_list=recipients,
    )


class Command(VerboseCommand):
    help = 'Monitor a PACER report and send emails when there are results.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--sleep',
            required=True,
            type=int,
            help="How long to wait between checks."
        )
        parser.add_argument(
            '--recipients',
            required=True,
            help="A comma-separated list of emails to send to"
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)

        recipients = options['recipients'].split(',')
        print("Recipients list is: %s" % recipients)

        s = PacerSession(username=settings.PACER_USERNAME,
                         password=settings.PACER_PASSWORD)
        s.login()
        report = CaseQueryAdvancedBankruptcy('canb', s)
        t1 = now()
        while True:
            report.query(
                name_last='Pacific',
                filed_from=datetime.date(2019, 1, 28),
                filed_to=datetime.date(2019, 1, 30),
            )
            if len(report.data) > 0:
                send_emails(report, recipients)
                print("Got %s results and sent emails" % len(report.metadata))
                exit(0)

            report.query(
                name_last='PG&E',
                filed_from=datetime.date(2019, 1, 28),
                filed_to=datetime.date(2019, 1, 30),
            )
            if len(report.data) > 0:
                send_emails(report, recipients)
                print("Got %s results and sent emails" % len(report.metadata))
                exit(0)

            time.sleep(options['sleep'])
            t2 = now()
            min_login_frequency = 60 * 30  # thirty minutes
            if (t2 - t1).seconds > min_login_frequency:
                print("Logging in again.")
                t1 = now()
