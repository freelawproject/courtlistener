from django.contrib.auth.models import User
from django.utils.timezone import utc, make_aware

from django.core.mail import send_mass_mail
from django.core.management.base import BaseCommand
from django.template import Context, loader
from optparse import make_option

from datetime import datetime, timedelta
import logging
import sys


logger = logging.getLogger(__name__)


def list_option_callback(option, opt, value, parser):
    setattr(parser.values, option.dest, value.split(','))


class Command(BaseCommand):
    option_list = BaseCommand.option_list + (
        make_option(
            '--simulate',
            action='store_true',
            default=False,
            help='Don\'t send any emails, just pretend.',
        ),
    )
    help = 'Sends a welcome email to the people who signed up in the last 24 hours.'

    def send_emails(self, recipients):
        """Send the emails using the templates and contexts requested."""
        messages = []
        email_subject = 'Hi from CourtListener and Free Law Project'
        email_sender = 'Brian Carver <bcarver@courtListener.com>'
        txt_template = loader.get_template('emails/welcome_email.txt')
        for recipient in recipients:
            c = Context({'name': recipient.first_name,})
            email_txt = txt_template.render(c)
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
            sys.stdout.write('Simulation mode. Imagine that we just sent the welcome emails!\n')

    def handle(self, *args, **options):
        self.options = options
        recipients = User.objects.filter(date_joined__gt=make_aware(datetime.now(), utc) - timedelta(days=1))
        if recipients:
            if self.options['simulate']:
                sys.stdout.write("**********************************\n")
                sys.stdout.write("* SIMULATE MODE - NO EMAILS SENT *\n")
                sys.stdout.write("**********************************\n")
            self.send_emails(recipients)
