import datetime
import hashlib
import random
from cl.users.models import UserProfile
from cl.users.utils import emails
from django.contrib.sites.models import Site
from django.core.mail import send_mail
from django.core.management import BaseCommand
from django.utils.timezone import now


class Command(BaseCommand):
    help = ('Notify users of unconfirmed accounts and delete accounts that '
            'were never confirmed')

    def add_arguments(self, parser):
        parser.add_argument(
            '--notify',
            action='store_true',
            default=False,
            help='Notify users with unconfirmed accounts older than five days, '
                 'and delete orphaned profiles.'
        )
        parser.add_argument(
            '--delete',
            action='store_true',
            default=False,
            help='Delete unconfirmed accounts older than two months'
        )
        parser.add_argument(
            '--simulate',
            action='store_true',
            default=False,
            help='Simulate the emails that would be sent, using the console '
                 'backend. Do not delete accounts.'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            default=False,
            help="Create more output."
        )

    def handle(self, *args, **options):
        self.options = options
        if options['delete']:
            self.delete_old_accounts()
        if options['notify']:
            self.notify_unconfirmed_accounts()
        if options['simulate']:
            print "**************************************"
            print "* NO EMAILS SENT OR ACCOUNTS DELETED *"
            print "**************************************"

    def delete_old_accounts(self):
        """Find accounts older than roughly two months that have not been
        confirmed, and delete them. Should be run once a month, or so.
        """
        two_months_ago = now() - datetime.timedelta(60)
        unconfirmed_ups = UserProfile.objects.filter(
            email_confirmed=False,
            user__date_joined__lte=two_months_ago,
            stub_account=False,
        )

        for up in unconfirmed_ups:
            user = up.user.username
            if self.options['verbose']:
                print "User %s deleted" % user
            if not self.options['simulate']:
                # Gather their foreign keys, delete those
                up.alert.all().delete()
                up.donation.all().delete()
                up.favorite.all().delete()

                # delete the user then the profile.
                up.user.delete()
                up.delete()

    def notify_unconfirmed_accounts(self):
        """This function will notify people who have not confirmed their
        accounts that they must do so for fear of deletion.

        This function should be run once a week, or so.

        Because it updates the expiration date of the user's key, and also uses
        that field to determine if the user should be notified in the first
        place, the first week, a user will have an old enough key, and will be
        notified, but the next week their key will have a very recent
        expiration date (because it was just updated the prior week). This
        means that they won't be selected the next week, but the one after,
        their key will be old again, and they will be selected. It's not ideal,
        but it's OK.
        """

        # if your account is more than a week old, and you have not confirmed
        # it, we will send you a notification, requesting that you confirm it.
        a_week_ago = now() - datetime.timedelta(7)
        unconfirmed_ups = UserProfile.objects.filter(
            email_confirmed=False,
            key_expires__lte=a_week_ago,
            stub_account=False
        )

        for up in unconfirmed_ups:
            if self.options['verbose']:
                print "User %s will be notified" % up.user

            if not self.options['simulate']:
                # Build and save a new activation key for the account.
                salt = hashlib.sha1(str(random.random())).hexdigest()[:5]
                activation_key = hashlib.sha1(
                    salt + up.user.username).hexdigest()
                key_expires = now() + datetime.timedelta(5)
                up.activation_key = activation_key
                up.key_expires = key_expires
                up.save()

                # Send the email.
                current_site = Site.objects.get_current()
                email = emails['email_not_confirmed']
                send_mail(
                    email['subject'] % current_site.name,
                    email['body'] % (up.user.username, up.activation_key),
                    email['from'],
                    [up.user.email]
                )
