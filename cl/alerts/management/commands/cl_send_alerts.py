import datetime
import traceback

from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q
from django.http import QueryDict
from django.template import loader
from django.utils.timezone import now

from cl.alerts.models import Alert, RealTimeQueue
from cl.lib import search_utils
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.scorched_utils import ExtraSolrInterface
from cl.lib.search_utils import regroup_snippets
from cl.search.forms import SearchForm
from cl.stats.utils import tally_stat

# Only do this number of RT items at a time. If there are more, they will be
# handled in the next run of this script.
MAX_RT_ITEM_QUERY = 1000


class InvalidDateError(Exception):
    pass


def get_cut_off_date(rate, d=datetime.date.today()):
    """Given a rate of dly, wly or mly and a date, returns the date after which
    new results should be considered a hit for an cl.
    """
    cut_off_date = None
    if rate == Alert.REAL_TIME:
        # use a couple days ago to limit results without risk of leaving out
        # important items (this will be filtered further later).
        cut_off_date = d - datetime.timedelta(days=10)
    elif rate == Alert.DAILY:
        cut_off_date = d
    elif rate == Alert.WEEKLY:
        cut_off_date = d - datetime.timedelta(days=7)
    elif rate == Alert.MONTHLY:
        if datetime.date.today().day > 28:
            raise InvalidDateError('Monthly alerts cannot be run on the 29th, '
                                   '30th or 31st.')

        # Get the first of the month of the previous month regardless of the
        # current date
        early_last_month = d - datetime.timedelta(days=28)
        cut_off_date = datetime.datetime(early_last_month.year,
                                         early_last_month.month, 1)
    return cut_off_date


def send_alert(user_profile, hits):
    email_subject = '[CourtListener] New hits for your alerts'
    email_sender = 'CourtListener Alerts <alerts@courtlistener.com>'

    txt_template = loader.get_template('email.txt')
    html_template = loader.get_template('email.html')
    context = {'hits': hits}
    txt = txt_template.render(context)
    html = html_template.render(context)
    msg = EmailMultiAlternatives(email_subject, txt, email_sender,
                                 [user_profile.user.email])
    msg.attach_alternative(html, "text/html")
    msg.send(fail_silently=False)


class Command(VerboseCommand):
    help = 'Sends the alert emails on a real time, daily, weekly or monthly ' \
           'basis.'

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)
        self.connections = {
            'o': ExtraSolrInterface(settings.SOLR_OPINION_URL, mode='r'),
            'oa': ExtraSolrInterface(settings.SOLR_AUDIO_URL, mode='r'),
            'r': ExtraSolrInterface(settings.SOLR_RECAP_URL, mode='r'),
        }
        self.options = {}
        self.valid_ids = {}

    def add_arguments(self, parser):
        parser.add_argument(
            '--rate',
            required=True,
            choices=Alert.ALL_FREQUENCIES,
            help="The rate to send emails (%s)" %
                 ', '.join(Alert.ALL_FREQUENCIES),
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        self.options = options
        if options['rate'] == Alert.REAL_TIME:
            self.remove_stale_rt_items()
            self.valid_ids = self.get_new_ids()

        self.send_emails(options['rate'])
        if options['rate'] == Alert.REAL_TIME:
            self.clean_rt_queue()

    def run_query(self, alert, rate):
        results = []
        error = False
        cd = {}
        logger.info("Now running the query: %s\n" % alert.query)

        # Make a dict from the query string. Make a copy to make it mutable.
        data = QueryDict(alert.query).copy()
        try:
            del data['filed_before']
        except KeyError:
            pass
        data['order_by'] = 'score desc'
        logger.info("Data sent to SearchForm is: %s\n" % data)
        search_form = SearchForm(data)
        if search_form.is_valid():
            cd = search_form.cleaned_data

            if rate == Alert.REAL_TIME and \
                    len(self.valid_ids[cd['type']]) == 0:
                # Bail out. No results will be found if no valid_ids.
                return error, cd['type'], results

            cut_off_date = get_cut_off_date(rate)
            if cd['type'] == 'o':
                cd['filed_after'] = cut_off_date
            elif cd['type'] == 'oa':
                cd['argued_after'] = cut_off_date
            main_params = search_utils.build_main_query(cd, facet=False)
            main_params.update({
                'rows': '20',
                'start': '0',
                'hl.tag.pre': '<em><strong>',
                'hl.tag.post': '</strong></em>',
                'caller': 'cl_send_alerts',
            })

            if rate == Alert.REAL_TIME:
                main_params['fq'].append('id:(%s)' % ' OR '.join(
                    [str(i) for i in self.valid_ids[cd['type']]]
                ))
            results = self.connections[
                cd['type']
            ].query().add_extra(
                **main_params
            ).execute()
            regroup_snippets(results)

        logger.info("There were %s results\n" % len(results))
        return cd.get('type'), results

    def send_emails(self, rate):
        """Send out an email to every user whose alert has a new hit for a
        rate.
        """
        users = User.objects.filter(alerts__rate=rate).distinct()

        alerts_sent_count = 0
        for user in users:
            alerts = user.alerts.filter(rate=rate)
            logger.info("Running alerts for user '%s': %s" % (user, alerts))

            not_donated_enough = user.profile.total_donated_last_year < \
                settings.MIN_DONATION['rt_alerts']
            if not_donated_enough and rate == Alert.REAL_TIME:
                logger.info('User: %s has not donated enough for their %s '
                            'RT alerts to be sent.\n' % (user, alerts.count()))
                continue

            hits = []
            for alert in alerts:
                try:
                    alert_type, results = self.run_query(alert, rate)
                except:
                    traceback.print_exc()
                    logger.info("Search for this alert failed: %s\n" %
                                alert.query)
                    continue

                # hits is a multi-dimensional array. It consists of alerts,
                # paired with a list of document dicts, of the form:
                # [[alert1, [{hit1}, {hit2}, {hit3}]], [alert2, ...]]
                if len(results) > 0:
                    hits.append([alert, alert_type, results])
                    alert.date_last_hit = now()
                    alert.save()

            if len(hits) > 0:
                alerts_sent_count += 1
                send_alert(user.profile, hits)

        tally_stat('alerts.sent.%s' % rate, inc=alerts_sent_count)
        logger.info("Sent %s %s email alerts." % (alerts_sent_count, rate))

    def clean_rt_queue(self):
        """Clean out any items in the RealTime queue once they've been run or
        if they are stale.
        """
        q = Q()
        for item_type, ids in self.valid_ids.items():
            q |= Q(item_type=item_type, item_pk__in=ids)
        RealTimeQueue.objects.filter(q).delete()

    def remove_stale_rt_items(self, age=2):
        """Remove anything old from the RTQ.

        This helps avoid issues with solr hitting the maxboolean clause errors.

        :param age: How many days old should items be before we start deleting
        them?
        """
        RealTimeQueue.objects.filter(
            date_modified__lt=now() - datetime.timedelta(days=age),
        ).delete()

    def get_new_ids(self):
        """Get an intersection of the items that are new in the DB and those
        that have made it into Solr.

        For every item that's in the RealTimeQueue, query Solr and see which
        have made it to the index. We'll use these to run the alerts.

        Returns a dict like so:
            {
                'oa': [list, of, ids],
                'o': [list, of, ids],
            }
        """
        valid_ids = {}
        for item_type in RealTimeQueue.ALL_ITEM_TYPES:
            ids = RealTimeQueue.objects.filter(item_type=item_type)
            if ids:
                main_params = {
                    'q': '*',  # Vital!
                    'caller': 'cl_send_alerts:%s' % item_type,
                    'rows': MAX_RT_ITEM_QUERY,
                    'fl': 'id',
                    'fq': ['id:(%s)' % ' OR '.join(
                        [str(i.item_pk) for i in ids]
                    )],
                }
                results = self.connections[item_type].query().add_extra(
                    **main_params).execute()
                valid_ids[item_type] = [int(r['id']) for r in
                                        results.result.docs]
            else:
                valid_ids[item_type] = []
        return valid_ids
