import traceback
import settings
from django.core.management import setup_environ
setup_environ(settings)

from alert.lib import search_utils
from alert.lib import sunburnt
from alerts.models import FREQUENCY
from alert.search.forms import SearchForm
from userHandling.models import UserProfile

from django.template import loader, Context
from django.core.mail import send_mail, EmailMultiAlternatives

import datetime
from optparse import OptionParser


class InvalidDateError(Exception):
    pass


def send_alert(userProfile, hits, verbose, simulate):
    EMAIL_SUBJECT = 'New hits for your CourtListener alerts'
    EMAIL_SENDER = 'CourtListener Alerts <alerts@courtlistener.com>'

    if userProfile.plaintext_preferred:
        txt_template = loader.get_template('emails/email.txt')
        c = Context({'hits': hits})
        email_text = txt_template.render(c)
        if verbose and simulate:
            print "email_text: %s" % email_text
        if not simulate:
            send_mail(EMAIL_SUBJECT, email_text, EMAIL_SENDER,
                      [userProfile.user.email], fail_silently=False)
    else:
        txt_template = loader.get_template('emails/email.txt')
        html_template = loader.get_template('emails/email.html')
        c = Context({'hits': hits})
        email_text = txt_template.render(c)
        html_text = html_template.render(c)
        if verbose and simulate:
            print "email_text: %s" % email_text
            print "html_text: %s" % html_text
        if not simulate:
            msg = EmailMultiAlternatives(EMAIL_SUBJECT, email_text,
                EMAIL_SENDER, [userProfile.user.email])
            msg.attach_alternative(html_text, "text/html")
            msg.send(fail_silently=False)


def get_cut_off_date(rate):
    today = datetime.date.today()
    if rate == 'dly':
        cut_off_date = today
    elif rate == 'wly':
        cut_off_date = today - datetime.timedelta(days=7)
    elif rate == 'mly':
        if today.day > 28:
            raise InvalidDateError, 'Monthly alerts cannot be run on the 29th, 30th or 31st.'
        early_last_month = today - datetime.timedelta(days=28)
        cut_off_date = datetime.date(early_last_month.year, early_last_month.month, 1)
    return cut_off_date


def emailer(rate, verbose, simulate):
    """Send out an email to every user whose alert has a new hit for a rate.

    Look up all users that have alerts for a given period of time, and iterate
    over them. For each of their alerts that has a hit, build up an email that
    contains all the hits.

    It's tempting to lookup alerts and iterate over those instead of over the
    users. The problem with that is that it would send one email per *alert*,
    not per *user*.
    """

    conn = sunburnt.SolrInterface(settings.SOLR_URL, mode='r')
    cut_off_date = get_cut_off_date(rate)

    # Query all users with alerts of the desired frequency
    # Use the distinct method to only return one instance of each person.
    userProfiles = UserProfile.objects.filter(alert__alertFrequency=rate).distinct()

    # for each user with a daily, weekly or monthly alert...
    for userProfile in userProfiles:
        #...get their alerts...
        alerts = userProfile.alert.filter(alertFrequency=rate)
        if verbose:
            print "\n\nAlerts for user %s: %s" % (userProfile.user.email,
                                                  alerts)

        hits = []
        # ...and iterate over their alerts.
        for alert in alerts:
            try:
                if verbose:
                    print "Now running the query: %s" % alert.alertText

                # Set up the data
                data = search_utils.get_string_to_dict(alert.alertText)
                try:
                    del data['filed_before']
                except KeyError:
                    pass
                data['filed_after'] = cut_off_date
                data['sort'] = 'dateFiled desc'
                if verbose:
                    print "Data sent to SearchForm is: %s" % data
                search_form = SearchForm(data)
                if search_form.is_valid():
                    cd = search_form.cleaned_data
                    main_params = search_utils.build_main_query(cd)
                    main_params['rows'] = '25'
                    main_params['start'] = '0'
                    main_params['hl.tag.pre'] = '<em><strong>'
                    main_params['hl.tag.post'] = '</strong></em>'
                    results = conn.raw_query(**main_params).execute()
                else:
                    print "Query for alert %s was invalid" % alert.alertText
                    print "Errors from the SearchForm: %s" % search_form.errors
                    continue
            except:
                traceback.print_exc()
                print "Search for this alert failed: %s" % alert.alertText
                continue

            if verbose:
                print "The value of results is: %s" % results
                print "The there were %s results" % len(results)

            # hits is a multi-dimensional array. It consists of alerts,
            # paired with a list of document dicts, of the form:
            # [[alert1, [{hit1}, {hit2}, {hit3}]], [alert2, ...]]
            try:
                if len(results) > 0:
                    hits.append([alert, results])
                    alert.lastHitDate = datetime.date.today()
                    alert.save()
                elif alert.sendNegativeAlert:
                    # if they want an alert even when no hits.
                    hits.append([alert, None])
                    if verbose:
                        print "Sending results for negative alert %s" % alert.alertName
            except Exception, e:
                print "Search failed on this alert: %s" % alert.alertText
                print e

        if len(hits) > 0:
            send_alert(userProfile, hits, verbose, simulate)
        elif verbose:
            print "No hits, thus not sending mail for this alert."

    return "Done"


def main():
    usage = "usage: %prog -r RATE [--verbose] [--simulate]"
    parser = OptionParser(usage)
    parser.add_option('-r', '--rate', dest='rate', metavar='RATE',
        help="The rate to send emails (%s)" % ', '.join(dict(FREQUENCY).keys()))
    parser.add_option('-v', '--verbose', action="store_true", dest='verbose',
        default=False, help="Display variable values during execution (note"
                            " that this can cause UnicodeEncodeErrors)")
    parser.add_option('-s', '--simulate', action="store_true",
        dest='simulate', default=False, help="Simulate the emails that " + \
        "would be sent, using the console backend")
    (options, args) = parser.parse_args()
    if not options.rate:
        parser.error("You must specify a rate")
    if options.rate not in dict(FREQUENCY).keys():
        parser.error("Invalid rate. Rate must be one of: %s" % ', '.join(dict(FREQUENCY).keys()))
    rate = options.rate
    verbose = options.verbose
    simulate = options.simulate

    if simulate:
        print "**********************************"
        print "* SIMULATE MODE - NO EMAILS SENT *"
        print "**********************************"

    return emailer(rate, verbose, simulate)


if __name__ == '__main__':
    main()

