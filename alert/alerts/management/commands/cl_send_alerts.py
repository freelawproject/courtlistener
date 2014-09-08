import os
import sys
from django.core.management import BaseCommand
from django.utils.timezone import now

execfile('/etc/courtlistener')
sys.path.append(INSTALL_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
from django.conf import settings

import logging
import traceback

from alert.lib import search_utils
from alert.lib import sunburnt
from alert.alerts.models import FREQUENCY
from alert.search.forms import SearchForm
from alert.stats import tally_stat
from alert.userHandling.models import UserProfile

from django.core.mail import EmailMultiAlternatives
from django.template import loader, Context

import datetime
from optparse import make_option


logger = logging.getLogger(__name__)


class InvalidDateError(Exception):
    pass


def get_cut_off_date(rate, d=datetime.date.today()):
    if rate == 'dly':
        cut_off_date = d
    elif rate == 'wly':
        cut_off_date = d - datetime.timedelta(days=7)
    elif rate == 'mly':
        if datetime.date.today().day > 28:
            raise InvalidDateError, 'Monthly alerts cannot be run on the 29th, 30th or 31st.'
        # Get the first of the month of the previous month regardless of the current date
        early_last_month = d - datetime.timedelta(days=28)
        cut_off_date = datetime.datetime(early_last_month.year, early_last_month.month, 1)
    return cut_off_date


class Command(BaseCommand):
    option_list = BaseCommand.option_list + (
        make_option(
            '--rate',
            help="The rate to send emails (%s)" % ', '.join(dict(FREQUENCY).keys()),
        ),
        make_option(
            '--simulate',
            action='store_true',
            default=False,
            help='Simulate the emails that would be sent using the console backend.',
        ),
        make_option(
            '--date',
            help="The date that you want to send alerts for (for debugging, applies simulate mode).",
        ),
        make_option(
            '--user_id',
            help="A particular user id you want to run the alerts for (debug)."
        ),
    )
    help = 'Sends the alert emails on a daily, weekly or monthly basis.'
    args = '--rate (dly|wly|mly) [--simulate] [--date YYYY-MM-DD] [--user USER]'

    def send_alert(self, userProfile, hits):
        EMAIL_SUBJECT = 'New hits for your CourtListener alerts'
        EMAIL_SENDER = 'CourtListener Alerts <alerts@courtlistener.com>'

        txt_template = loader.get_template('alerts/email.txt')
        html_template = loader.get_template('alerts/email.html')
        c = Context({'hits': hits})
        txt = txt_template.render(c)
        html = html_template.render(c)
        msg = EmailMultiAlternatives(EMAIL_SUBJECT, txt,
                                     EMAIL_SENDER, [userProfile.user.email])
        msg.attach_alternative(html, "text/html")
        if not self.options['simulate']:
            msg.send(fail_silently=False)

    def emailer(self, cut_off_date):
        """Send out an email to every user whose alert has a new hit for a rate.

        Look up all users that have alerts for a given period of time, and iterate
        over them. For each of their alerts that has a hit, build up an email that
        contains all the hits.

        It's tempting to lookup alerts and iterate over those instead of over the
        users. The problem with that is that it would send one email per *alert*,
        not per *user*.
        """

        # Query all users with alerts of the desired frequency
        # Use the distinct method to only return one instance of each person.
        if self.options.get('user_id'):
            userProfiles = UserProfile.objects.filter(alert__alertFrequency=self.options['rate']).\
                filter(user__pk=self.options['user_id']).distinct()
        else:
            userProfiles = UserProfile.objects.filter(alert__alertFrequency=self.options['rate']).distinct()

        # for each user with a daily, weekly or monthly alert...
        alerts_sent_count = 0
        for userProfile in userProfiles:
            #...get their alerts...
            alerts = userProfile.alert.filter(alertFrequency=self.options['rate'])
            if self.verbosity >= 1:
                print "\n\nAlerts for user '%s': %s" % (userProfile.user, alerts)
                print "*" * 40

            hits = []
            # ...and iterate over their alerts.
            for alert in alerts:
                try:
                    if self.verbosity >= 1:
                        print "Now running the query: %s" % alert.alertText

                    # Set up the data
                    data = search_utils.get_string_to_dict(alert.alertText)
                    try:
                        del data['filed_before']
                    except KeyError:
                        pass
                    data['filed_after'] = cut_off_date
                    data['order_by'] = 'score desc'
                    if self.verbosity >= 1:
                        print "Data sent to SearchForm is: %s" % data
                    search_form = SearchForm(data)
                    if search_form.is_valid():
                        cd = search_form.cleaned_data
                        main_params = search_utils.build_main_query(cd, 'opinion')
                        main_params.update({
                            'rows': '20',
                            'start': '0',
                            'hl.tag.pre': '<em><strong>',
                            'hl.tag.post': '</strong></em>',
                            'caller': 'cl_send_alerts',
                        })
                        results = self.conn.raw_query(**main_params).execute()
                    else:
                        print "Query for alert %s was invalid" % alert.alertText
                        print "Errors from the SearchForm: %s" % search_form.errors
                        continue
                except:
                    traceback.print_exc()
                    print "Search for this alert failed: %s" % alert.alertText
                    continue

                if self.verbosity >= 1:
                    print "There were %s results" % len(results)
                if self.verbosity >= 2:
                    print "The value of results is: %s" % results

                # hits is a multi-dimensional array. It consists of alerts,
                # paired with a list of document dicts, of the form:
                # [[alert1, [{hit1}, {hit2}, {hit3}]], [alert2, ...]]
                try:
                    if len(results) > 0:
                        hits.append([alert, results])
                        alert.lastHitDate = now()
                        alert.save()
                    elif alert.sendNegativeAlert:
                        # if they want an alert even when no hits.
                        hits.append([alert, None])
                        if self.verbosity >= 1:
                            print "Sending results for negative alert '%s'" % alert.alertName
                except Exception, e:
                    traceback.print_exc()
                    print "Search failed on this alert: %s" % alert.alertText
                    print e

            if len(hits) > 0:
                alerts_sent_count += 1
                self.send_alert(userProfile, hits)
            elif self.verbosity >= 1:
                print "No hits, thus not sending mail for this alert."

        if not self.options['simulate']:
            tally_stat('alerts.sent.%s' % self.options['rate'], inc=alerts_sent_count)
            logger.info("Sent %s %s email alerts." % (alerts_sent_count, self.options['rate']))

    def handle(self, *args, **options):
        self.verbosity = int(options.get('verbosity', 1))
        self.conn = sunburnt.SolrInterface(settings.SOLR_OPINION_URL, mode='r')
        self.options = options
        if not options.get('rate'):
            self.stderr.write("You must specify a rate")
            exit(1)
        if options['rate'] not in dict(FREQUENCY).keys():
            self.stderr.write("Invalid rate. Rate must be one of: %s" % ', '.join(dict(FREQUENCY).keys()))
        if options.get('user_id'):
            try:
                options['user_id'] = int(options['user_id'])
            except ValueError:
                self.stderr.write("user_id must be an ID parsable as an int.")
        if options.get('date'):
            # Enable simulate mode if a date is provided.
            options['simulate'] = True
        if options.get('date'):
            try:
                # Midnight of day requested
                cut_off_date = get_cut_off_date(options['rate'], datetime.datetime.strptime(options['date'], '%Y-%m-%d'))
            except ValueError:
                self.stderr.write("Invalid date string. Format should be YYYY-MM-DD.")
        else:
            cut_off_date = get_cut_off_date(options['rate'])

        if options.get('simulate'):
            print "**********************************"
            print "* SIMULATE MODE - NO EMAILS SENT *"
            print "**********************************"

        return self.emailer(cut_off_date)

