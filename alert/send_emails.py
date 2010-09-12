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
from userHandling.models import FREQUENCY
from search.views import preparseQuery
from alertSystem.models import Document
from django.template import loader, Context
from django.core.mail import send_mail, EmailMultiAlternatives

import calendar
import datetime
import time
from optparse import OptionParser


def emailer(rate, verbose, simulate):
    """This will load all the users each day/week/month, and send them
    emails."""
    # remap the FREQUENCY variable from the model so the human keys relate
    # back to the indices
    rates = {}
    for r in FREQUENCY:
        rates[r[1].lower()] = r[0]
    RATE = rates[rate]

    # sphinx likes time in UnixTime format, which the below accomplishes.
    # There doesn't appear to be an easier way to do this. The output can be
    # tested in the shell with: date --date="2010-04-16" +%s
    today = datetime.date.today()
    unixTimeToday = int(time.mktime(today.timetuple()))
    unixTimesPastWeek = []
    unixTimesPastMonth = []
    i = 0
    while i < 7:
        unixTimesPastWeek.append(unixTimeToday - (86400 * i))
        i += 1
    i = 0
    while i < calendar.mdays[datetime.date.today().month]:
        unixTimesPastMonth.append(unixTimeToday - (86400 * i))
        i += 1

    EMAIL_SUBJECT = 'New hits for your alert at CourtListener.com'
    EMAIL_SENDER = 'no-reply@courtlistener.com'

    # query all users with alerts of the desired frequency
    # use the distinct method to only return one instance of each person.
    userProfiles = UserProfile.objects.filter(alert__alertFrequency = RATE)\
        .distinct()

    if verbose:
        print "today: " + str(today)
        print "unixTimeToday: " + str(unixTimeToday)
        print "unixTimesPastWeek: " + str(unixTimesPastWeek)
        print "unixTimesPastMonth: " + str(unixTimesPastMonth)
        print "userProfiles (with " + rate + " alerts): " + str(userProfiles)

    # for each user with a daily, weekly or monthly alert...
    for userProfile in userProfiles:
        #...get their alerts...
        alerts = userProfile.alert.filter(alertFrequency = RATE)
        if verbose:
            print "\n\n" + rate + " alerts for user " + userProfile.user\
                .email + ": " + str(alerts)

        hits = []
        # ...and iterate over their alerts.
        for alert in alerts:
            query = preparseQuery(alert.alertText)

            try:
                if verbose:
                    print "Now running the query: " + query
                if RATE == 'dly':
                    # query the alert
                    if verbose:
                        "Now running the search for: " + query
                    queryset = Document.search.query(query)
                    results = queryset.set_options(
                        mode="SPH_MATCH_EXTENDED2")\
                        .filter(datefiled=unixTimeToday)
                elif RATE == 'wly' and today.weekday() == 6:
                    # if it's a weekly alert and today is Sunday
                    if verbose:
                        "Now running the search for: " + query
                    queryset = Document.search.query(query)
                    results = queryset.set_options(
                        mode="SPH_MATCH_EXTENDED2")\
                        .filter(datefiled=unixTimesPastWeek)
                elif RATE == 'mly' and today.day == 19:
                    # if it's a monthly alert and today is the first of the
                    # month
                    if verbose:
                        "Now running the search for: " + query
                    queryset = Document.search.query(query)
                    results = queryset.set_options(
                        mode="SPH_MATCH_EXTENDED2")\
                        .filter(datefiled=unixTimesPastMonth)
                elif RATE == "off":
                    pass
            except:
                # search occasionally barfs. We need to log this.
                print "Search barfed on this alert: " + query
                continue


            if verbose:
                print "The value of results is: " + str(results)
                print "The value of results.count() is: " + \
                    str(results.count())
                print "There were " + str(results.count()) + \
                " hits for the alert \"" + query + \
                "\". Here are the first 0-20: " + str(results)

            # hits is a multidimensional array. Ugh. It consists of alerts,
            # paired with a list of documents, of the form:
            # [[alert1, [hit1, hit2, hit3, hit4]], [alert2, [hit1, hit2]]]
            try:
                if results.count() > 0:
                    # very important! if you don't do the slicing here, you'll
                    # only get the first 20 hits. also very frustrating!
                    alertWithResults = [alert, results[0:results.count()]]
                    hits.append(alertWithResults)
                    # set the hit date to today
                    alert.lastHitDate = datetime.date.today()
                    alert.save()
                    if verbose:
                        print "alertWithResults: " + str(alertWithResults)
                        print "hits: " + str(hits)

                elif alert.sendNegativeAlert:
                    # if they want an alert even when no hits.
                    alertWithResults = [alert, "None"]
                    hits.append(alertWithResults)

                    if verbose:
                        print "Sending results for negative alert, " + \
                            query + "."
                        print "alertWithResults: " + str(alertWithResults)
                        print "hits: " + str(hits)
            except:
                print "Search barfed on this alert: " + query

        if len(hits) > 0:
            # either the hits var has the value "None", or it has hits.
            if userProfile.plaintextPreferred:
                # send a plaintext email.
                txtTemplate = loader.get_template('emails/email.txt')
                c = Context({
                    'hits': hits,
                })
                email_text = txtTemplate.render(c)

                if verbose and simulate:
                    print "email_text: " + str(email_text)

                if not simulate:
                    send_mail(
                        EMAIL_SUBJECT,
                        email_text,
                        EMAIL_SENDER,
                        [userProfile.user.email],
                        fail_silently=False)
            else:
                # send a multi-part email
                txtTemplate = loader.get_template('emails/email.txt')
                htmlTemplate = loader.get_template('emails/email.html')
                c = Context({
                    'hits': hits,
                })
                email_text = txtTemplate.render(c)
                html_text = htmlTemplate.render(c)

                if verbose and simulate:
                    print "email_text: " + str(email_text)
                    print "html_text: " + str(html_text)

                if not simulate:
                    msg = EmailMultiAlternatives(EMAIL_SUBJECT, email_text,
                        EMAIL_SENDER, [userProfile.user.email])
                    msg.attach_alternative(html_text, "text/html")
                    msg.send(fail_silently=False)
        elif verbose:
            print "Not sending mail for this alert."


    return "Done"


def main():
    usage = "usage: %prog -r RATE [--verbose] [--simulate]"
    parser = OptionParser(usage)
    parser.add_option('-r', '--rate', dest='rate', metavar='RATE',
        help="The rate to send emails")
    parser.add_option('-v', '--verbose', action="store_true", dest='verbose',
        default=False, help="Display variable values during execution")
    parser.add_option('-s', '--simulate', action="store_true",
        dest='simulate', default=False, help="Simulate the emails that " +\
        "would be sent, using the console backend")
    (options, args) = parser.parse_args()
    if not options.rate:
        parser.error("You must specify a rate")

    rate = options.rate
    verbose = options.verbose
    simulate = options.simulate

    if simulate:
        print "******************"
        print "* NO EMAILS SENT *"
        print "******************"

    return emailer(rate, verbose, simulate)


if __name__ == '__main__':
    main()
