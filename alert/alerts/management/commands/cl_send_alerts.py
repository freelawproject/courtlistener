import os
import sys

execfile('/etc/courtlistener')
sys.path.append(INSTALL_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
from django.conf import settings

import datetime
import logging
import traceback

from alert.alerts.models import FREQUENCY, RealTimeQueue, ITEM_TYPES
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
    cut_off_date = None
    if rate == 'rt':
        # use a couple days ago to limit results without risk of leaving out
        # important items (this will be filtered further later).
        cut_off_date = d - datetime.timedelta(days=2)
    elif rate == 'dly':
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


def send_alert(user_profile, hits, simulate):
    email_subject = 'New hits for your CourtListener alerts'
    email_sender = 'CourtListener Alerts <alerts@courtlistener.com>'

    txt_template = loader.get_template('alerts/email.txt')
    html_template = loader.get_template('alerts/email.html')
    c = Context({'hits': hits})
    txt = txt_template.render(c)
    html = html_template.render(c)
    msg = EmailMultiAlternatives(email_subject, txt, email_sender,
                                 [user_profile.user.email])
    msg.attach_alternative(html, "text/html")
    if not simulate:
        msg.send(fail_silently=False)


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
    )
    help = 'Sends the alert emails on a daily, weekly or monthly basis.'
    args = ('--rate (dly|wly|mly) [--simulate] [--date YYYY-MM-DD] '
            '[--user USER]')

    def run_query(self, alert):
        results = []
        error = False
        try:
            logger.info("Now running the query: %s\n" % alert.query)

            # Set up the data
            data = search_utils.get_string_to_dict(alert.query)
            try:
                del data['filed_before']
            except KeyError:
                pass
            data['order_by'] = 'score desc'
            logger.info("  Data sent to SearchForm is: %s\n" % data)
            search_form = SearchForm(data)
            if search_form.is_valid():
                cd = search_form.cleaned_data

                if self.rate == 'rt' and len(self.valid_ids[cd['type']]) == 0:
                    # Bail out. No results will be found if no valid_ids.
                    return error, cd['type'], results

                cut_off_date = get_cut_off_date(self.rate)
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
                if self.rate == 'rt':
                    main_params['fq'].append(
                        'id:(%s)' % ' OR '.join(
                            [str(i) for i in self.valid_ids[cd['type']]]
                        ),
                    )
                results = self.connections[
                    cd['type']
                ].raw_query(
                    **main_params
                ).execute()
            else:
                logger.info("  Query for alert %s was invalid\n"
                            "  Errors from the SearchForm: %s\n" %
                            (alert.query, search_form.errors))
                error = True
        except:
            traceback.print_exc()
            logger.info("  Search for this alert failed: %s\n" %
                        alert.query)
            error = True

        logger.info("  There were %s results\n" % len(results))

        return error, cd['type'], results

    def send_emails(self):
        """Send out an email to every user whose alert has a new hit for a
        rate.
        """
        ups = UserProfile.objects.filter(
            alert__rate=self.rate,
        ).distinct()

        alerts_sent_count = 0
        for up in ups:
            not_donated_enough = up.total_donated_last_year < \
                settings.MIN_DONATION['rt_alerts']
            if not_donated_enough and self.rate == 'rt':
                logger.info('\n\nUser: %s has not donated enough for their %s RT '
                            'alerts to be sent.\n' % (up.user, len(alerts)))
                continue

            alerts = up.alert.filter(rate=self.rate)
            logger.info("\n\nAlerts for user '%s': %s\n"
                        "%s\n" % (up.user, alerts, '*' * 40))

            hits = []
            for alert in alerts:
                error, type, results = self.run_query(alert)
                if error:
                    continue

                # hits is a multi-dimensional array. It consists of alerts,
                # paired with a list of document dicts, of the form:
                # [[alert1, [{hit1}, {hit2}, {hit3}]], [alert2, ...]]
                try:
                    if len(results) > 0:
                        hits.append([alert, type, results])
                        alert.date_last_hit = now()
                        alert.save()
                    elif len(results) == 0 and alert.always_send_email:
                        hits.append([alert, type, None])
                        logger.info("  Sending results for negative alert "
                                    "'%s'\n" % alert.name)
                except Exception, e:
                    traceback.print_exc()
                    logger.info("  Search failed on this alert: %s\n%s\n" %
                                (alert.query, e))

            if len(hits) > 0:
                alerts_sent_count += 1
                send_alert(up, hits, self.options['simulate'])
            elif self.verbosity >= 1:
                logger.info("  No hits. Not sending mail for this alert.\n")

        if not self.options['simulate']:
            tally_stat('alerts.sent.%s' % self.rate, inc=alerts_sent_count)
            logger.info("Sent %s %s email alerts." %
                        (alerts_sent_count, self.rate))

    def clean_rt_queue(self):
        """Clean out any items in the RealTime queue once they've been run or
        if they are stale.
        """
        if self.rate == 'rt' and not self.options['simulate']:
            for type, ids in self.valid_ids.iteritems():
                RealTimeQueue.objects.filter(
                    item_type=type,
                    item_pk__in=ids,
                ).delete()

            RealTimeQueue.objects.filter(
                date_modified__lt=now() - datetime.timedelta(days=7),
            ).delete()

    def get_new_ids(self):
        """For every item that's in the RealTimeQueue, query Solr and
        see which have made it to the index. We'll use these to run the alerts.

        Returns a dict like so:
            {
                'oa': [list, of, ids],
                'o': [list, of, ids],
            }
        """
        valid_ids = {}
        for type in [t[0] for t in ITEM_TYPES]:
            ids = RealTimeQueue.objects.filter(item_type=type)
            if ids:
                main_params = {
                    'caller': 'cl_send_alerts',
                    'fl': 'id',
                    'fq': ['id:(%s)' % ' OR '.join(
                        [str(i.item_pk) for i in ids]
                    )],
                }
                results = self.connections[type].raw_query(**main_params).execute()
                valid_ids[type] = [int(r['id']) for r in results.result.docs]
            else:
                valid_ids[type] = []
        return valid_ids

    def handle(self, *args, **options):
        self.verbosity = int(options.get('verbosity', 1))
        self.options = options
        self.rate = options.get('rate')
        if not self.rate:
            self.stderr.write("You must specify a rate")
            exit(1)
        if self.rate not in dict(FREQUENCY).keys():
            self.stderr.write("Invalid rate. Rate must be one of: %s" %
                              ', '.join(dict(FREQUENCY).keys()))
            exit(1)

        self.connections = {
            'o': sunburnt.SolrInterface(settings.SOLR_OPINION_URL, mode='r'),
            'oa': sunburnt.SolrInterface(settings.SOLR_AUDIO_URL, mode='r'),
        }

        if self.rate == 'rt':
            self.valid_ids = self.get_new_ids()

        if self.options['simulate']:
            logger.info("******************************************\n"
                        "* SIMULATE MODE - NO EMAILS WILL BE SENT *\n"
                        "******************************************\n")

        self.send_emails()
        self.clean_rt_queue()


