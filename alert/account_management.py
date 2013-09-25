import settings
from django.core.management import setup_environ
setup_environ(settings)

from userHandling.models import UserProfile
from django.contrib.sites.models import Site
from django.core.mail import send_mail

import datetime
import hashlib
import random
from optparse import OptionParser


def delete_old_accounts(verbose, simulate):
    """
    This script will find accounts older than roughly two months that have
    not been confirmed, and delete them. It can be run once a month, or so.
    """
    two_months_ago = (datetime.date.today() - datetime.timedelta(60))
    unconfirmed_ups = UserProfile.objects.filter(
        email_confirmed=False,
        user__date_joined__lte=two_months_ago,
        stub_account=False,
    )

    for up in unconfirmed_ups:
        user = str(up.user.username)
        if verbose:
            print "User %s deleted." % user
        if not simulate:
            # Gather their foreign keys, delete those
            up.alert.all().delete()
            up.donation.all().delete()
            up.favorite.all().delete()

            # delete the user then the profile.
            up.user.delete()
            up.delete()

    return 0


def notify_unconfirmed(verbose, simulate):
    """This function will notify people who have not confirmed their accounts
    that they must do so for fear of the deletion bots (above). This function
    should be run once a week, or so.

    Because it updates the expiration date of the user's key, and also uses
    that field to determine if the user should be notified in the first place,
    the first week, a user will have an old enough key, and will be notified,
    but the next week their key will have a very recent expiration date
    (because it was just updated the prior week). This means that they won't
    be selected the next week, but the one after, their key will be old again,
    and they will be selected. It's not ideal, but it's OK."""

    # if your account is more than a week old, and you have not confirmed it,
    # we will send you a notification, requesting that you confirm it.
    a_week_ago = (datetime.date.today() - datetime.timedelta(7))

    # get the accounts
    unconfirmed_ups = UserProfile.objects.filter(
        email_confirmed=False,
        key_expires__lte=a_week_ago,
        stub_account=False
    )

    for up in unconfirmed_ups:
        if verbose:
            print "User %s will be notified" % up.user

        if not simulate:
            # Build and save a new activation key for the account.
            salt = hashlib.sha1(str(random.random())).hexdigest()[:5]
            activation_key = hashlib.sha1(salt + up.user.username).hexdigest()
            key_expires = datetime.datetime.today() + datetime.timedelta(5)
            up.activation_key = activation_key
            up.key_expires = key_expires
            up.save()

            # Send the email.
            current_site = Site.objects.get_current()
            email_subject = 'Please confirm your account on ' + \
                str(current_site.name)
            email_body = ("Hello, %s,\n\nDuring routine maintenance of our site, we discovered that your email address "
                          "has not yet been confirmed. To confirm your email address and continue using our site, "
                          "please click the following link:\n\n"
                          " - https://www.courtlistener.com/email/confirm/%s\n\n"
                          "Unfortuantely, accounts that are not confirmed will stop receiving alerts, and must "
                          "eventually be deleted from our system.\n\n"
                          "Thanks for using our site,\n\n"
                          "The CourtListener team\n\n\n"
                          "------------------\n"
                          "For questions or comments, please see our contact page, "
                          "https://www.courtlistener.com/contact/." % (up.user.username, up.activation_key))
            send_mail(email_subject, email_body, 'CourtListener <noreply@courtlistener.com>', [up.user.email])
    return 0


def main():
    usage = "usage: %prog [--verbose] [--simulate]"
    parser = OptionParser(usage)
    parser.add_option(
        '-n',
        '--notify',
        action="store_true",
        dest='notify',
        default=False,
        help="Notify users with unconfirmed accounts older five days and delete orphaned profiles."
    )
    parser.add_option(
        '-d',
        '--delete',
        action="store_true",
        dest='delete',
        default=False,
        help="Delete unconfirmed accounts older than two months."
    )
    parser.add_option(
        '-v',
        '--verbose',
        action="store_true",
        dest='verbose',
        default=False,
        help="Display variable values during execution"
    )
    parser.add_option(
        '-s',
        '--simulate',
        action="store_true",
        dest='simulate',
        default=False,
        help="Simulate the emails that would be sent, using the console backend. Do not delete accounts."
    )
    (options, args) = parser.parse_args()

    verbose = options.verbose
    simulate = options.simulate
    delete = options.delete
    notify = options.notify

    if delete:
        delete_old_accounts(verbose, simulate)
    if notify:
        notify_unconfirmed(verbose, simulate)
    if simulate:
        print "**************************************"
        print "* NO EMAILS SENT OR ACCOUNTS DELETED *"
        print "**************************************"

    return 0


if __name__ == '__main__':
    main()
