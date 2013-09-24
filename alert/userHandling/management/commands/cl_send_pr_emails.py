import ast
from alert import settings
from alert.stats import tally_stat
from alert.userHandling.models import UserProfile

from django.core.mail import send_mass_mail
from django.core.management.base import BaseCommand
from django.template import Context, loader
from optparse import make_option

import datetime
import logging
import sys


logger = logging.getLogger(__name__)


def list_option_callback(option, opt, value, parser):
    setattr(parser.values, option.dest, value.split(','))


class Command(BaseCommand):


    option_list = BaseCommand.option_list + (
        make_option(
            '--subscribers',
            default=False,
            action='store_true',
            help='Lookup the subscribers in the database and send the email to them.'
        ),
        make_option(
            '--recipients',
            type='string',
            action='callback',
            callback=list_option_callback,
            help='A list of recipients you wish to send the email to as comma separated values.'
        ),
        make_option(
            '--subject',
            type='string',
            help='The subject of the email you wish to send.',
        ),
        make_option(
            '--sender',
            type='string',
            default=settings.DEFAULT_FROM_EMAIL,
            help='The sender for the email, default is from your settings.py file.'
        ),
        make_option(
            '--template',
            help='What is the path, relative to the template directory, where your email template lives?'
        ),
        make_option(
            '--context',
            default='{}',
            help='A dict containing the context for the email, if desired.'
        ),
        make_option(
            '--simulate',
            action='store_true',
            default=False,
            help='Don\'t send any emails, just pretend.',
        )
    )
    help = 'Sends a PR email to the people listed in recipients field and/or that are subscribed to the CL newsletter'

    def send_emails(self, recipients):
        """Send the emails using the templates and contexts requested."""
        email_subject = self.options['subject']
        email_sender = self.options['sender']
        txt_template = loader.get_template(self.options['template'])
        c = Context(ast.literal_eval(self.options['context']))
        email_txt = txt_template.render(c)

        emails_sent_count = 0
        messages = []
        for recipient in recipients:
            messages.append((
                email_subject,
                email_txt,
                email_sender,
                [recipient],
            ))
            emails_sent_count += 1

        if not self.options['simulate']:
            send_mass_mail(messages, fail_silently=False)
            tally_stat('pr.emails.sent', inc=emails_sent_count)
            logger.info("Sent %s pr emails." % emails_sent_count)
        else:
            sys.stdout.write('Simulation mode. Imagine that we just sent %s emails!\n' % emails_sent_count)

    def handle(self, *args, **options):
        self.verbosity = int(options.get('verbosity', 1))
        self.options = options

        recipients = []

        if options.get('subscribers'):
            for up in UserProfile.objects.filter(wants_newsletter=True):
                recipients.append(up.user.email)
        if options.get('recipients'):
            recipients.extend(options['recipients'])
        if not options['subject']:
            sys.stderr.write('No subject provided. Aborting.\n')
            exit(1)
        if not options['template']:
            sys.stderr.write('No template provided. Aborting.\n')
            exit(1)
        if recipients:
            if options['simulate']:
                sys.stdout.write("**********************************\n")
                sys.stdout.write("* SIMULATE MODE - NO EMAILS SENT *\n")
                sys.stdout.write("**********************************\n")
            recipients = list(set(recipients))  # Dups gotta go.
            self.send_emails(recipients)
        else:
            sys.stderr.write("No recipients defined. Aborting.\n")
            exit(1)
