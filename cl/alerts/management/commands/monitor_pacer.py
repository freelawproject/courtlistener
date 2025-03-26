import asyncio
import datetime

from asgiref.sync import async_to_sync, sync_to_async
from django.conf import settings
from django.core.mail import send_mail
from django.template import loader
from django.utils.timezone import now
from juriscraper.pacer import CaseQueryAdvancedBankruptcy

from cl.lib.command_utils import VerboseCommand
from cl.lib.pacer_session import ProxyPacerSession


def send_emails(report, recipients):
    subject = "The PG&E Bankruptcy is Posted"
    template = loader.get_template("pacer_alert_email.txt")
    context = {"report": report}
    send_mail(
        subject=subject,
        message=template.render(context),
        from_email=settings.DEFAULT_ALERTS_EMAIL,
        recipient_list=recipients,
    )


class Command(VerboseCommand):
    help = "Monitor a PACER report and send emails when there are results."

    def add_arguments(self, parser):
        parser.add_argument(
            "--sleep",
            required=True,
            type=int,
            help="How long to wait between checks.",
        )
        parser.add_argument(
            "--recipients",
            required=True,
            help="A comma-separated list of emails to send to",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)

        recipients = options["recipients"].split(",")
        print(f"Recipients list is: {recipients}")

        async_to_sync(self.monitor)(recipients, options["sleep"])

    async def monitor(self, recipients: list[str], sleep: int) -> None:
        """Poll until results arrive, keeping login and queries on one loop."""
        async with ProxyPacerSession(
            username=settings.PACER_USERNAME, password=settings.PACER_PASSWORD
        ) as s:
            await s.login()
            report = CaseQueryAdvancedBankruptcy("canb", s)
            t1 = now()
            while True:
                query = "Pacific"
                await report.query(
                    name_last=query,
                    filed_from=datetime.date(2019, 1, 28),
                    filed_to=datetime.date(2019, 1, 30),
                )
                num_results = len(report.data)
                print(f"Checked '{query}' and got {num_results} results")
                if num_results > 0:
                    print("Sending emails and exiting!")
                    await sync_to_async(send_emails)(report, recipients)
                    return

                query = "PG&E"
                await report.query(
                    name_last=query,
                    filed_from=datetime.date(2019, 1, 28),
                    filed_to=datetime.date(2019, 1, 30),
                )
                num_results = len(report.data)
                print(f"Checked '{query}' and got {num_results} results")
                if num_results > 0:
                    print("Sending emails and exiting!")
                    await sync_to_async(send_emails)(report, recipients)
                    return

                await asyncio.sleep(sleep)
                t2 = now()
                min_login_frequency = 60 * 30  # thirty minutes
                if (t2 - t1).seconds > min_login_frequency:
                    print("Logging in again.")
                    await s.login()
                    t1 = now()
