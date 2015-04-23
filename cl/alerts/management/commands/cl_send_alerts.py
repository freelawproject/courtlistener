import datetime
import logging
import traceback

from cl.alerts.models import FREQUENCY, RealTimeQueue, ITEM_TYPES
from cl.lib import search_utils
from cl.lib import sunburnt
from cl.search.forms import SearchForm
from cl.stats import tally_stat

from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand
from django.template import loader
from django.utils.timezone import now

logger = logging.getLogger(__name__)


class InvalidDateError(Exception):
    pass


def get_cut_off_date(rate, d=datetime.date.today()):
    """Given a rate of dly, wly or mly and a date, returns the date after which
    new results should be considered a hit for an cl.
    """
    cut_off_date = None
    if rate == 'rt':
        # use a couple days ago to limit results without risk of leaving out
        # important items (this will be filtered further later).
        cut_off_date = d - datetime.timedelta(days=10)
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

    txt_template = loader.get_template('email.txt')
    html_template = loader.get_template('email.html')
    context = {'hits': hits}
    txt = txt_template.render(context)
    html = html_template.render(context)
    msg = EmailMultiAlternatives(email_subject, txt, email_sender,
                                 [user_profile.user.email])
    msg.attach_alternative(html, "text/html")
    if not simulate:
        msg.send(fail_silently=False)


class Command(BaseCommand):
    help = 'Sends the alert emails on a daily, weekly or monthly basis.'

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)
        self.connections = {
            'o': sunburnt.SolrInterface(settings.SOLR_OPINION_URL, mode='r'),
            'oa': sunburnt.SolrInterface(settings.SOLR_AUDIO_URL, mode='r'),
        }
        self.options = {}
        self.valid_ids = {}

    def add_arguments(self, parser):
        parser.add_argument(
            '--rate',
            required=True,
            choices=dict(FREQUENCY).keys(),
            help="The rate to send emails (%s)" %
                 ', '.join(dict(FREQUENCY).keys()),
        )
        parser.add_argument(
            '--simulate',
            action='store_true',
            default=False,
            help='Simulate the emails that would be sent using the console '
                 'backend.',
        )

    def run_query(self, alert, rate):
        results = []
        error = False
        cd = {}
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

                if rate == 'rt' and len(self.valid_ids[cd['type']]) == 0:
                    # Bail out. No results will be found if no valid_ids.
                    return error, cd['type'], results

                cut_off_date = get_cut_off_date(rate)
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
                if rate == 'rt':
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

        return error, cd.get('type'), results

    def send_emails(self, rate):
        """Send out an email to every user whose alert has a new hit for a
        rate.
        """
        users = User.objects.filter(
            alerts__rate=rate,
        ).distinct()

        alerts_sent_count = 0
        for user in users:
            alerts = user.alerts.filter(rate=rate)
            logger.info("\n\nAlerts for user '%s': %s\n"
                        "%s\n" % (user, alerts, '*' * 40))

            not_donated_enough = user.profile.total_donated_last_year < \
                settings.MIN_DONATION['rt_alerts']
            if not_donated_enough and rate == 'rt':
                logger.info('\n\nUser: %s has not donated enough for their %s '
                            'RT alerts to be sent.\n' % (user, len(alerts)))
                continue

            hits = []
            for alert in alerts:
                error, alert_type, results = self.run_query(alert, rate)
                if error:
                    continue

                # hits is a multi-dimensional array. It consists of alerts,
                # paired with a list of document dicts, of the form:
                # [[alert1, [{hit1}, {hit2}, {hit3}]], [alert2, ...]]
                try:
                    if len(results) > 0:
                        hits.append([alert, alert_type, results])
                        alert.date_last_hit = now()
                        alert.save()
                    # elif len(results) == 0 and alert.always_send_email:
                    #     hits.append([alert, alert_type, None])
                    #     logger.info("  Sending results for negative alert "
                    #                 "'%s'\n" % alert.name)
                except Exception, e:
                    traceback.print_exc()
                    logger.info("  Search failed on this alert: %s\n%s\n" %
                                (alert.query, e))

            if len(hits) > 0:
                alerts_sent_count += 1
                send_alert(user.profile, hits, self.options['simulate'])
            elif self.options['verbosity'] >= 1:
                logger.info("  No hits. Not sending mail for this cl.\n")

        if not self.options['simulate']:
            tally_stat('alerts.sent.%s' % rate, inc=alerts_sent_count)
            logger.info("Sent %s %s email alerts." %
                        (alerts_sent_count, rate))

    def clean_rt_queue(self, rate):
        """Clean out any items in the RealTime queue once they've been run or
        if they are stale.
        """
        if rate == 'rt' and not self.options['simulate']:
            for item_type, ids in self.valid_ids.items():
                RealTimeQueue.objects.filter(
                    item_type=item_type,
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
        for item_type in [t[0] for t in ITEM_TYPES]:
            ids = RealTimeQueue.objects.filter(item_type=item_type)
            if ids:
                main_params = {
                    'q': '*:*',  # Vital!
                    'caller': 'cl_send_alerts',
                    'rows': 1000,
                    'fl': 'id',
                    'fq': ['id:(%s)' % ' OR '.join(
                        [str(i.item_pk) for i in ids]
                    )],
                }
                results = self.connections[item_type].raw_query(
                    **main_params).execute()
                valid_ids[item_type] = [int(r['id']) for r in
                                        results.result.docs]
            else:
                valid_ids[item_type] = []
        return valid_ids

    def handle(self, *args, **options):
        self.options = options
        if options['rate'] == 'rt':
            self.valid_ids = self.get_new_ids()

        if options['simulate']:
            logger.info("******************************************\n"
                        "* SIMULATE MODE - NO EMAILS WILL BE SENT *\n"
                        "******************************************\n")

        self.send_emails(options['rate'])
        self.clean_rt_queue(options['rate'])
