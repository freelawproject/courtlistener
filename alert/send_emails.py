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


from userHandling.models import Alert, UserProfile
from userHandling.models import FREQUENCY
from alertSystem.models import Document
from django.contrib.auth.models import User
from django.http import HttpResponseRedirect, HttpResponse
from django.shortcuts import render_to_response
from django.template import RequestContext, loader, Context
from django.core.mail import send_mail, EmailMultiAlternatives

import datetime, time, calendar
from optparse import OptionParser

def emailer(rate):
    """This will load all the users each day/week/month, and send them emails."""
    # remap the FREQUENCY variable from the model so the human keys relate back
    # to the indices
    rates = {}
    for r in FREQUENCY:
        rates[r[1].lower()] = r[0]
    RATE = rates[rate]

    # sphinx likes time in UnixTime format, which the below accomplishes. Sadly,
    # there doesn't appear to be an easier way to do this. The output can be
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
    userProfiles = UserProfile.objects.filter(alert__alertFrequency = RATE).distinct()

    # for each user with a daily, weekly or monthly alert...
    for userProfile in userProfiles:
        #...get their alerts...
        alerts = userProfile.alert.filter(alertFrequency = RATE)

        hits = []
        # ...and iterate over their alerts.
        for alert in alerts:
            if RATE == 'dly':
                # query the alert
                queryset = Document.search.query(alert.alertText)
                results = queryset.set_options(mode="SPH_MATCH_EXTENDED2")\
                    .filter(datefiled=unixTimeToday)
            elif RATE == 'wly' and today.weekday() == 6:
                # if it's a weekly alert and today is Sunday
                queryset = Document.search.query(alert.alertText)
                results = queryset.set_options(mode="SPH_MATCH_EXTENDED2")\
                    .filter(datefiled=unixTimesPastWeek)
            elif RATE == 'mly' and today.day == 19:
                # if it's a monthly alert and today is the first of the month
                queryset = Document.search.query(alert.alertText)
                results = queryset.set_options(mode="SPH_MATCH_EXTENDED2")\
                    .filter(datefiled=unixTimesPastMonth)
            elif RATE == "off":
                pass


            # hits is a multidimensional array. Ugh.
            # it consists of alerts, paired with a list of documents, of the form:
            # [[alert1, [hit1, hit2, hit3, hit4]], [alert2, [hit1, hit2]]]
            if results.count() > 0:
                # very important! if you don't do the slicing here, you'll only
                # get the first 20 hits. also very frustrating!
                alertWithResults = [alert, results[0:results.count()]]
                hits.append(alertWithResults)
                # set the hit date to today
                alert.lastHitDate = datetime.date.today()
                alert.save()
            elif alert.sendNegativeAlert:
                # if they want an alert even when no hits.
                alertWithResults = [alert, "None"]
                hits.append(alertWithResults)

        if userProfile.plaintextPreferred:
            # send a plaintext email.
            txtTemplate = loader.get_template('emails/email.txt')
            c = Context({
                'hits': hits,
            })
            email_text = txtTemplate.render(c)

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

            msg = EmailMultiAlternatives(EMAIL_SUBJECT, email_text, EMAIL_SENDER, [userProfile.user.email])
            msg.attach_alternative(html_text, "text/html")

            msg.send(fail_silently=False)

    return "Done"


def main():
    usage = "usage: %prog -r RATE | --rate=RATE"
    parser = OptionParser(usage)
    parser.add_option('-r', '--rate', dest='rate', metavar='RATE',
                      help="The rate to send emails")
    (options, args) = parser.parse_args()
    if not options.rate:
        parser.error("You must specify a rate")

    rate = options.rate

    return emailer(rate)


if __name__ == '__main__':
    main()
