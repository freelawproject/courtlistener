import logging
import sys
from datetime import datetime, timedelta
from django.contrib.auth.models import User
from django.core.mail import send_mass_mail
from django.core.management.base import BaseCommand
from django.template import loader
from django.utils.timezone import utc, make_aware

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Note that this entire command can be replaced with scheduled celery
    tasks. Instead of running this once daily, you just schedule a task for
    later when somebody signs up.
    """
    help = ('Sends a welcome email to the people who signed up in the last '
            '24 hours.')

    def add_arguments(self, parser):
        parser.add_argument(
            '--simulate',
            action='store_true',
            default=False,
            help='Don\'t send any emails, just pretend.',
        )

    def handle(self, *args, **options):
        self.options = options
        yesterday = make_aware(datetime.now(), utc) - timedelta(days=1)
        recipients = User.objects.filter(
            date_joined__gt=yesterday,
        )
        if recipients:
            if self.options['simulate']:
                sys.stdout.write(
                    "**********************************\n"
                    "* SIMULATE MODE - NO EMAILS SENT *\n"
                    "**********************************\n"
                )
            self.send_emails(recipients)

    def send_emails(self, recipients):
        """Send the emails using the templates and contexts requested."""
        messages = []
        email_subject = 'Hi from CourtListener and Free Law Project'
        email_sender = 'Brian Carver <bcarver@courtListener.com>'
        txt_template = loader.get_template('emails/welcome_email.txt')
        for recipient in recipients:
            context = {'name': recipient.first_name}
            email_txt = txt_template.render(context)
            messages.append((
                email_subject,
                email_txt,
                email_sender,
                [recipient.email],
            ))

        if not self.options['simulate']:
            send_mass_mail(messages, fail_silently=False)
            logger.info("Sent daily welcome emails.")
        else:
            sys.stdout.write('Simulation mode. Imagine that we just sent the '
                             'welcome emails!\n')
