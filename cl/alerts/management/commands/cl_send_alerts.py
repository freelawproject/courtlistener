import datetime
import traceback
import warnings

from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q
from django.http import QueryDict
from django.template import loader
from django.utils.timezone import now

from cl.alerts.models import Alert, RealTimeQueue
from cl.alerts.utils import InvalidDateError
from cl.api.models import WebhookEventType
from cl.api.webhooks import send_search_alert_webhook
from cl.lib import search_utils
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.scorched_utils import ExtraSolrInterface
from cl.lib.search_utils import regroup_snippets
from cl.search.forms import SearchForm
from cl.search.models import SEARCH_TYPES
from cl.stats.utils import tally_stat

# Only do this number of RT items at a time. If there are more, they will be
# handled in the next run of this script.
MAX_RT_ITEM_QUERY = 1000


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
            raise InvalidDateError(
                "Monthly alerts cannot be run on the 29th, 30th or 31st."
            )

        # Get the first of the month of the previous month regardless of the
        # current date
        early_last_month = d - datetime.timedelta(days=28)
        cut_off_date = datetime.datetime(
            early_last_month.year, early_last_month.month, 1
        )
    return cut_off_date


def send_alert(user_profile, hits):
    subject = "New hits for your alerts"

    txt_template = loader.get_template("alert_email.txt")
    html_template = loader.get_template("alert_email.html")
    context = {"hits": hits}
    txt = txt_template.render(context)
    html = html_template.render(context)
    msg = EmailMultiAlternatives(
        subject, txt, settings.DEFAULT_ALERTS_EMAIL, [user_profile.user.email]
    )
    msg.attach_alternative(html, "text/html")
    msg.send(fail_silently=False)


class Command(VerboseCommand):
    help = (
        "Sends the alert emails on a real time, daily, weekly or monthly "
        "basis."
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sis = {
            SEARCH_TYPES.OPINION: ExtraSolrInterface(
                settings.SOLR_OPINION_URL, mode="r"
            ),
            SEARCH_TYPES.ORAL_ARGUMENT: ExtraSolrInterface(
                settings.SOLR_AUDIO_URL, mode="r"
            ),
            SEARCH_TYPES.RECAP: ExtraSolrInterface(
                settings.SOLR_RECAP_URL, mode="r"
            ),
        }
        self.options = {}
        self.valid_ids = {}

    def __del__(self):
        for si in self.sis.values():
            si.conn.http_connection.close()

    def add_arguments(self, parser):
        parser.add_argument(
            "--rate",
            required=True,
            choices=Alert.ALL_FREQUENCIES,
            help=f"The rate to send emails ({', '.join(Alert.ALL_FREQUENCIES)})",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        self.options = options
        if options["rate"] == Alert.REAL_TIME:
            self.remove_stale_rt_items()
            self.valid_ids = self.get_new_ids()

        self.send_emails_and_webhooks(options["rate"])
        if options["rate"] == Alert.REAL_TIME:
            self.clean_rt_queue()

    def run_query(self, alert, rate):
        results = []
        cd = {}
        logger.info(f"Now running the query: {alert.query}\n")

        # Make a dict from the query string.
        qd = QueryDict(alert.query.encode(), mutable=True)
        try:
            del qd["filed_before"]
        except KeyError:
            pass
        qd["order_by"] = "score desc"
        cut_off_date = get_cut_off_date(rate)
        # Default to 'o', if not available, according to the front end.
        query_type = qd.get("type", SEARCH_TYPES.OPINION)
        if query_type in [SEARCH_TYPES.OPINION, SEARCH_TYPES.RECAP]:
            qd["filed_after"] = cut_off_date
        elif query_type == SEARCH_TYPES.ORAL_ARGUMENT:
            qd["argued_after"] = cut_off_date
        logger.info(f"Data sent to SearchForm is: {qd}\n")
        search_form = SearchForm(qd)
        if search_form.is_valid():
            cd = search_form.cleaned_data

            if (
                rate == Alert.REAL_TIME
                and len(self.valid_ids[query_type]) == 0
            ) or (
                rate == Alert.REAL_TIME
                and query_type == SEARCH_TYPES.ORAL_ARGUMENT
            ):
                # Bail out. No results will be found if no valid_ids.
                return query_type, results

            main_params = search_utils.build_main_query(
                cd,
                highlight="text",  # Required to show all field as in Search API
                facet=False,
            )
            main_params.update(
                {
                    "rows": "20",
                    "start": "0",
                    "hl.tag.pre": "<em><strong>",
                    "hl.tag.post": "</strong></em>",
                    "caller": f"cl_send_alerts:{query_type}",
                }
            )

            if rate == Alert.REAL_TIME:
                main_params["fq"].append(
                    f"id:({' OR '.join([str(i) for i in self.valid_ids[query_type]])})"
                )

            # Ignore warnings from this bit of code. Otherwise, it complains
            # about the query URL being too long and having to POST it instead
            # of being able to GET it.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                results = (
                    self.sis[query_type]
                    .query()
                    .add_extra(**main_params)
                    .execute()
                )
            regroup_snippets(results)

        logger.info(f"There were {len(results)} results.")
        return qd, results

    def send_emails_and_webhooks(self, rate):
        """Send out an email and webhook events to every user whose alert has a
        new hit for a rate.
        """
        users = User.objects.filter(alerts__rate=rate).distinct()

        alerts_sent_count = 0
        for user in users:
            alerts = user.alerts.filter(rate=rate)
            logger.info(f"Running alerts for user '{user}': {alerts}")

            not_donated_enough = (
                user.profile.total_donated_last_year
                < settings.MIN_DONATION["rt_alerts"]
            )
            if not_donated_enough and rate == Alert.REAL_TIME:
                logger.info(
                    "User: %s has not donated enough for their %s "
                    "RT alerts to be sent.\n" % (user, alerts.count())
                )
                continue

            hits = []
            for alert in alerts:
                try:
                    qd, results = self.run_query(alert, rate)
                except:
                    traceback.print_exc()
                    logger.info(
                        f"Search for this alert failed: {alert.query}\n"
                    )
                    continue

                # hits is a multi-dimensional array. It consists of alerts,
                # paired with a list of document dicts, of the form:
                # [[alert1, [{hit1}, {hit2}, {hit3}]], [alert2, ...]]
                if len(results) > 0:
                    search_type = qd.get("type", SEARCH_TYPES.OPINION)
                    hits.append([alert, search_type, results])
                    alert.query_run = qd.urlencode()
                    alert.date_last_hit = now()
                    alert.save()

                    # Send webhook event if the user has a SEARCH_ALERT
                    # endpoint enabled.
                    user_webhooks = user.webhooks.filter(
                        event_type=WebhookEventType.SEARCH_ALERT, enabled=True
                    )
                    for user_webhook in user_webhooks:
                        send_search_alert_webhook(
                            self.sis[search_type], results, user_webhook, alert
                        )

            if len(hits) > 0:
                alerts_sent_count += 1
                send_alert(user.profile, hits)

        tally_stat(f"alerts.sent.{rate}", inc=alerts_sent_count)
        logger.info(f"Sent {alerts_sent_count} {rate} email alerts.")

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
        for item_type in SEARCH_TYPES.ALL_TYPES:
            ids = RealTimeQueue.objects.filter(item_type=item_type)
            if ids:
                main_params = {
                    "q": "*",  # Vital!
                    "caller": f"cl_send_alerts:{item_type}",
                    "rows": MAX_RT_ITEM_QUERY,
                    "fl": "id",
                    "fq": [
                        f"id:({' OR '.join([str(i.item_pk) for i in ids])})"
                    ],
                }
                results = (
                    self.sis[item_type]
                    .query()
                    .add_extra(**main_params)
                    .execute()
                )
                valid_ids[item_type] = [
                    int(r["id"]) for r in results.result.docs
                ]
            else:
                valid_ids[item_type] = []
        return valid_ids
