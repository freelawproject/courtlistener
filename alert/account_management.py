# This software and any associated files are copyright 2010 Brian Carver and
# Michael Lissner.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import settings
from django.core.management import setup_environ
setup_environ(settings)

from userHandling.models import UserProfile
from django.contrib.auth.models import User
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

    # get the accounts
    unconfirmed_ups = UserProfile.objects.filter(emailConfirmed = False,
        user__date_joined__lte = two_months_ago.isoformat())

    # some redundant code here, but emphasis is on getting it right.
    for up in unconfirmed_ups:
        try:
            user = str(up.user.username)
            if verbose:
                print "User \"" + user + "\" deleted."
            if not simulate:
                # Gather their foreign keys, delete those, then delete their
                # profile and user info
                alerts = up.alert.all()
                for alert in alerts:
                    alert.delete()

                # delete the user then the profile.
                up.user.delete()
                up.delete()
        except:
            if verbose:
                print "Deleting orphaned profile, " + str(up)
            if not simulate:
                # it's an orphan user profile, so we delete it and any alerts
                # attached to it.
                alerts = up.alert.all()
                for alert in alerts:
                    alert.delete()

                # delete the profile.
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
    unconfirmed_ups = UserProfile.objects.filter(emailConfirmed = False,
        key_expires__lte = a_week_ago)

    for up in unconfirmed_ups:
        if verbose:
            try:
                print "User \"" + str(up.user) + "\" will be notified."
            except User.DoesNotExist:
                # the user profile doesn't have a profile attached to it
                # anymore due to deletion.
                print "***No user id on user_profile %s. Orphaned profile deleted.***" % up.userProfileUUID
                if not simulate:
                    alerts = up.alert.all()
                    for alert in alerts:
                        alert.delete()
                    up.delete()
                continue

        if not simulate:
            user = up.user
            # Build and save a new activation key for the account.
            salt = hashlib.sha1(str(random.random())).hexdigest()[:5]
            activationKey = hashlib.sha1(salt+user.username).hexdigest()
            key_expires = datetime.datetime.today() + datetime\
                    .timedelta(5)
            up.activationKey = activationKey
            up.key_expires = key_expires
            up.save()

            # Send the email.
            current_site = Site.objects.get_current()
            email_subject = 'Please confirm your account on ' + \
                str(current_site.name)
            email_body = "Hello, %s,\n\nDuring routine maintenance of our \
site, we discovered that your email address has not yet been confirmed. \
To confirm your email address and continue using our site, please click the \
following link:\n\nhttp://courtlistener.com/email/confirm/%s\n\n\
Unfortuantely, accounts that are not confirmed will stop receiving alerts, \
and must eventually be deleted from our system.\n\n\
Thanks for using our site,\n\nThe CourtListener team\n\n\n\
-------------------\nFor questions or comments, please see our contact page, \
http://courtlistener.com/contact/." % (
                user.username,
                up.activationKey)
            send_mail(email_subject,
                      email_body,
                      'no-reply@courtlistener.com',
                      [user.email])
    return 0


def generate_keys_expiration_dates():
    # generate keys expiration dates for accounts that lack them
    keyless = UserProfile.objects.filter(key_expires = None)

    for up in keyless:
        print "User \"" + up.user.username + \
            "\" got a new key expiration date."
        key_expires = datetime.datetime.today() + datetime\
                    .timedelta(5)
        up.key_expires = key_expires
        up.save()


def find_legit():
    # find accounts that have alerts, and mark them as confirmed.
    # this is a one-off script used to grandfather-in old accounts
    real_users = UserProfile.objects.filter(emailConfirmed = False)

    for user in real_users:
        if user.alert.count() > 0:
            print "User \"" + user.user.username + \
                "\" is toggled to confirmed."
            user.emailConfirmed = True
            user.save()

    return 0


def main():
    usage = "usage: %prog [--verbose] [--simulate]"
    parser = OptionParser(usage)
    parser.add_option('-g', '--grandfather', action='store_true',
        dest='grandfather', default=False, help="Grandfather in legit users.")
    parser.add_option('-n', '--notify', action="store_true", dest='notify',
        default=False, help="Notify users with unconfirmed accounts older " +\
        "five days and delete orphaned profiles.")
    parser.add_option('-d', '--delete', action="store_true", dest='delete',
        default=False, help="Delete unconfirmed accounts older than two " +\
        "months.")
    parser.add_option('-v', '--verbose', action="store_true", dest='verbose',
        default=False, help="Display variable values during execution")
    parser.add_option('-s', '--simulate', action="store_true",
        dest='simulate', default=False, help="Simulate the emails that " + \
        "would be sent, using the console backend. Do not delete accounts.")
    parser.add_option('-k', '--generate', action="store_true",
        dest="generate", default=False, help="Generate key expiration dates.")
    (options, args) = parser.parse_args()

    verbose = options.verbose
    simulate = options.simulate
    delete = options.delete
    notify = options.notify
    grandfather = options.grandfather
    generate = options.generate

    if grandfather:
        find_legit()
    if delete:
        delete_old_accounts(verbose, simulate)
    if notify:
        notify_unconfirmed(verbose, simulate)
    if generate:
        generate_keys_expiration_dates()
    if simulate:
        print "**************************************"
        print "* NO EMAILS SENT OR ACCOUNTS DELETED *"
        print "**************************************"

    return 0


if __name__ == '__main__':
    main()
