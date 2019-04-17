import sys
from datetime import datetime, timedelta

from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template import loader
from django.utils.timezone import utc, make_aware

from cl.lib.command_utils import VerboseCommand, logger


class Command(VerboseCommand):
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
        super(Command, self).handle(*args, **options)
        self.options = options
        yesterday = make_aware(datetime.now(), utc) - timedelta(days=1)
        recipients = User.objects.filter(date_joined__gt=yesterday,
                                         profile__stub_account=False)
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
        txt_template = loader.get_template('emails/welcome_email.txt')
        messages = []
        for recipient in recipients:
            email_txt = txt_template.render({'name': recipient.first_name})
            messages.append(EmailMultiAlternatives(
                subject='Welcome to CourtListener and Free Law Project',
                body=email_txt,
                from_email='Mike Lissner <mike@courtlistener.com>',
                to=[recipient.email],
                headers={'X-Entity-Ref-ID': 'welcome.email:%s' % recipient.pk}
            ))

        if not self.options['simulate']:
            connection = get_connection()
            connection.send_messages(messages)
            logger.info("Sent %s daily welcome emails." % len(messages))
        else:
            sys.stdout.write('Simulation mode. Imagine that we just sent %s '
                             'welcome emails!\n' % len(messages))
