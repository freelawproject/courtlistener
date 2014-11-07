import os
import sys

execfile('/etc/courtlistener')
sys.path.append(INSTALL_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
from django.conf import settings

import datetime
import logging
import traceback

from alert.alerts.models import FREQUENCY
from alert.lib import search_utils
from alert.lib import sunburnt
from alert.search.forms import SearchForm
from alert.stats import tally_stat
from alert.userHandling.models import UserProfile

from django.core.mail import EmailMultiAlternatives
from django.core.management import BaseCommand
from django.template import loader, Context
from django.utils.timezone import now
from optparse import make_option

logger = logging.getLogger(__name__)


class InvalidDateError(Exception):
    pass


def get_cut_off_date(rate, d=datetime.date.today()):
    """Given a rate of dly, wly or mly and a date, returns the date after which
    new results should be considered a hit for an alert.
    """
    if rate == 'dly':
        cut_off_date = d
    elif rate == 'wly':
        cut_off_date = d - datetime.timedelta(days=7)
    elif rate == 'mly':
        if datetime.date.today().day > 28:
            raise InvalidDateError('Monthly alerts cannot be run on the 29th, '
                                   '30th or 31st.')

        # Get the first of the month of the previous month regardless of the
        # current date
        early_last_month = d - datetime.timedelta(days=28)
        cut_off_date = datetime.datetime(early_last_month.year,
                                         early_last_month.month, 1)
    return cut_off_date


class Command(BaseCommand):
    option_list = BaseCommand.option_list + (
        make_option(
            '--rate',
            help="The rate to send emails (%s)" %
                 ', '.join(dict(FREQUENCY).keys()),
        ),
        make_option(
            '--simulate',
            action='store_true',
            default=False,
            help='Simulate the emails that would be sent using the console '
                 'backend.',
        ),
        make_option(
            '--date',
            help="The date that you want to send alerts for (for debugging, "
                 "applies simulate mode).",
        ),
        make_option(
            '--user_id',
            help="A particular user id you want to run the alerts for (debug)."
        ),
    )
    help = 'Sends the alert emails on a daily, weekly or monthly basis.'
    args = ('--rate (dly|wly|mly) [--simulate] [--date YYYY-MM-DD] '
            '[--user USER]')

    def send_alert(self, user_profile, hits):
        email_subject = 'New hits for your CourtListener alerts'
        email_sender = 'CourtListener Alerts <alerts@courtlistener.com>'

        txt_template = loader.get_template('alerts/email.txt')
        html_template = loader.get_template('alerts/email.html')
        c = Context({'hits': hits})
        txt = txt_template.render(c)
        html = html_template.render(c)
        msg = EmailMultiAlternatives(email_subject, txt,
                                     email_sender, [user_profile.user.email])
        msg.attach_alternative(html, "text/html")
        if not self.options['simulate']:
            msg.send(fail_silently=False)

    def run_query(self, alert, cut_off_date):
        results = None
        error = False
        try:
            if self.verbosity >= 1:
                print "Now running the query: %s" % alert.alertText

            # Set up the data
            data = search_utils.get_string_to_dict(alert.alertText)
            try:
                del data['filed_before']
            except KeyError:
                pass
            data['order_by'] = 'score desc'
            if self.verbosity >= 1:
                print "  Data sent to SearchForm is: %s" % data
            search_form = SearchForm(data)
            if search_form.is_valid():
                cd = search_form.cleaned_data
                if cd['type'] == 'o':
                    cd['filed_after'] = cut_off_date
                elif cd['type'] == 'oa':
                    cd['argued_after'] = cut_off_date
                main_params = search_utils.build_main_query(cd)
                main_params.update({
                    'rows': '20',
                    'start': '0',
                    'hl.tag.pre': '<em><strong>',
                    'hl.tag.post': '</strong></em>',
                    'caller': 'cl_send_alerts',
                })
                if cd['type'] == 'o':
                    conn = sunburnt.SolrInterface(
                        settings.SOLR_OPINION_URL, mode='r'
                    )
                elif cd['type'] == 'oa':
                    conn = sunburnt.SolrInterface(
                        settings.SOLR_AUDIO_URL, mode='r'
                    )
                results = conn.raw_query(**main_params).execute()
            else:
                print "  Query for alert %s was invalid" % alert.alertText
                print "  Errors from the SearchForm: %s" % search_form.errors
                error = True
        except:
            traceback.print_exc()
            print "  Search for this alert failed: %s" % alert.alertText
            error = True

        if self.verbosity >= 1:
            if results:
                print "  There were %s results" % len(results)
            else:
                print "  There were no results"
        if self.verbosity >= 2:
            print "  The value of results is: %s" % results

        return error, cd['type'], results,

    def emailer(self, ups, cut_off_date):
        """Send out an email to every user whose alert has a new hit for a
        rate.
        """

        # for each user with a daily, weekly or monthly alert...
        alerts_sent_count = 0
        for up in ups:
            # ...get their alerts...
            alerts = up.alert.filter(alertFrequency=self.options['rate'])
            if self.verbosity >= 1:
                print "\n\nAlerts for user '%s': %s" % (
                    up.user, alerts)
                print "*" * 40

            hits = []
            # ...and iterate over their alerts.
            for alert in alerts:
                error, type, results = self.run_query(alert, cut_off_date)
                if error:
                    continue

                # hits is a multi-dimensional array. It consists of alerts,
                # paired with a list of document dicts, of the form:
                # [[alert1, [{hit1}, {hit2}, {hit3}]], [alert2, ...]]
                try:
                    if len(results) > 0:
                        hits.append([alert, type, results])
                        alert.lastHitDate = now()
                        alert.save()
                    elif len(results) == 0 and alert.sendNegativeAlert:
                        # if they want an alert even when no hits.
                        hits.append([alert, type, None])
                        if self.verbosity >= 1:
                            print "  Sending results for negative alert '%s'" % \
                                  alert.alertName
                except Exception, e:
                    traceback.print_exc()
                    print "  Search failed on this alert: %s" % alert.alertText
                    print e

            if len(hits) > 0:
                alerts_sent_count += 1
                self.send_alert(up, hits)
            elif self.verbosity >= 1:
                print "  No hits, thus not sending mail for this alert."

        if not self.options['simulate']:
            tally_stat('alerts.sent.%s' % self.options['rate'],
                       inc=alerts_sent_count)
            logger.info("Sent %s %s email alerts." % (
                alerts_sent_count, self.options['rate']))

    def get_profiles(self):
        """Look up all users that have alerts for a given period of time.

        It's tempting to lookup alerts and iterate over those instead of over
        the users. The problem with that is that it would send one email per
        *alert*, not per *user*.
        """
        # Query all users with alerts of the desired frequency
        # Use the distinct method to only return one instance of each person.
        if self.options.get('user_id'):
            ups = UserProfile.objects.filter(
                alert__alertFrequency=self.options['rate']). \
                filter(user__pk=self.options['user_id']).distinct()
        else:
            ups = UserProfile.objects.filter(
                alert__alertFrequency=self.options['rate']).distinct()
        return ups

    def handle(self, *args, **options):
        self.verbosity = int(options.get('verbosity', 1))
        self.options = options
        if not options.get('rate'):
            self.stderr.write("You must specify a rate")
            exit(1)
        if options['rate'] not in dict(FREQUENCY).keys():
            self.stderr.write("Invalid rate. Rate must be one of: %s" %
                              ', '.join(dict(FREQUENCY).keys()))
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
                cut_off_date = get_cut_off_date(
                    options['rate'],
                    datetime.datetime.strptime(options['date'], '%Y-%m-%d')
                )
            except ValueError:
                self.stderr.write("Invalid date string. Format should be "
                                  "YYYY-MM-DD.")
        else:
            cut_off_date = get_cut_off_date(options['rate'])

        if options.get('simulate'):
            print "******************************************"
            print "* SIMULATE MODE - NO EMAILS WILL BE SENT *"
            print "******************************************"

        return self.emailer(self.get_profiles(), cut_off_date)

