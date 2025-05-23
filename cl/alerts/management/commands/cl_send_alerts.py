import calendar
import traceback
from datetime import date, timedelta
from urllib.parse import urlencode

from asgiref.sync import async_to_sync
from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives
from django.http import QueryDict
from django.template import loader
from django.urls import reverse
from django.utils.timezone import now
from elasticsearch_dsl import MultiSearch
from elasticsearch_dsl import Q as ES_Q
from elasticsearch_dsl.response import Response

from cl.alerts.models import Alert, RealTimeQueue
from cl.alerts.utils import InvalidDateError, build_alert_email_subject
from cl.api.models import WebhookEventType, WebhookVersions
from cl.api.webhooks import send_search_alert_webhook
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.elasticsearch_utils import (
    do_es_api_query,
    limit_inner_hits,
    set_child_docs_and_score,
    set_results_highlights,
)
from cl.lib.types import CleanData
from cl.search.constants import ALERTS_HL_TAG, SEARCH_ALERTS_OPINION_HL_FIELDS
from cl.search.documents import OpinionDocument
from cl.search.forms import SearchForm
from cl.search.models import SEARCH_TYPES
from cl.stats.utils import tally_stat

# Only do this number of RT items at a time. If there are more, they will be
# handled in the next run of this script.
MAX_RT_ITEM_QUERY = 1000


DAYS_WEEK = 7
DAYS_MONTH = 28


def get_cut_off_start_date(rate: str, d: date) -> date:
    """Calculate the cut-off start date based on the given rate and date.

    :param rate: The alert rate type.
    :param d: The reference date from which the cut-off start date is calculated.
    :return: The cut-off start date after which new results should be
    considered a hit for an alert.
    """
    match rate:
        case Alert.REAL_TIME:
            # use a couple of days ago to limit results without risk of leaving out
            # important items (this will be filtered further later).
            return d - timedelta(days=10)
        case Alert.DAILY:
            # For daily alerts: Set cut_off_date to the previous day since the
            # cron job runs early in the morning.
            return d - timedelta(days=1)
        case Alert.WEEKLY:
            return d - timedelta(days=DAYS_WEEK)
        case Alert.MONTHLY:
            if date.today().day > DAYS_MONTH:
                raise InvalidDateError(
                    "Monthly alerts cannot be run on the 29th, 30th, or 31st."
                )
            # Get the first day of the previous month, regardless of the
            # current date.
            early_last_month = d - timedelta(days=DAYS_MONTH)
            return date(early_last_month.year, early_last_month.month, 1)

        case _:
            raise NotImplementedError("Unsupported rate type: %s", rate)


def get_cut_off_end_date(rate: str, cutoff_start_date: date) -> date | None:
    """Given a rate of dly, wly, or mly and the cutoff_start_date, returns
    the cut-off end date to set the upper limit for the date range query.

    :param rate: The alert rate type.
    :param cutoff_start_date: The start date from which the cut-off end
    date is calculated.
    :return: The cut-off end date that serves as the upper limit for the date
    range query, or None if the rate is unsupported
    """

    match rate:
        case Alert.DAILY:
            return cutoff_start_date
        case Alert.WEEKLY:
            return cutoff_start_date + timedelta(days=DAYS_WEEK - 1)
        case Alert.MONTHLY:
            last_day = calendar.monthrange(
                cutoff_start_date.year, cutoff_start_date.month
            )[1]
            return date(
                cutoff_start_date.year, cutoff_start_date.month, last_day
            )
        case _:
            return None


def send_alert(user_profile, hits):
    subject = build_alert_email_subject(hits)
    txt_template = loader.get_template("alert_email_es.txt")
    html_template = loader.get_template("alert_email_es.html")
    context = {
        "hits": hits,
        "hits_limit": settings.SCHEDULED_ALERT_HITS_LIMIT,
    }

    headers = {}
    query_string = ""
    if len(hits) == 1:
        alert = hits[0][0]
        unsubscribe_path = reverse(
            "one_click_disable_alert", args=[alert.secret_key]
        )
        headers["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    else:
        params = {"keys": [hit[0].secret_key for hit in hits]}
        query_string = urlencode(params, doseq=True)
        unsubscribe_path = reverse("disable_alert_list")
    headers["List-Unsubscribe"] = (
        f"<https://www.courtlistener.com{unsubscribe_path}{'?' if query_string else ''}{query_string}>"
    )

    txt = txt_template.render(context)
    html = html_template.render(context)
    msg = EmailMultiAlternatives(
        subject,
        txt,
        settings.DEFAULT_ALERTS_EMAIL,
        [user_profile.user.email],
        headers=headers,
    )
    msg.attach_alternative(html, "text/html")
    msg.send(fail_silently=False)


def query_alerts_es(
    cd: CleanData, v1_webhook: bool = False
) -> tuple[Response, Response | None]:
    """Query ES for opinion alerts, optionally handling a V1 webhook query.

    :param cd: A CleanData object containing the query parameters.
    :param v1_webhook: A boolean indicating whether to include a V1 webhook query.
    :return: A tuple containing the main search response and an optional V1
    query response.
    """

    v1_results = None
    search_query = OpinionDocument.search()
    cd["highlight"] = True
    main_query, _ = do_es_api_query(
        search_query,
        cd,
        SEARCH_ALERTS_OPINION_HL_FIELDS,
        ALERTS_HL_TAG,
        "v4",
    )
    main_query = main_query.extra(
        from_=0,
        size=settings.SCHEDULED_ALERT_HITS_LIMIT,
    )
    multi_search = MultiSearch()
    multi_search = multi_search.add(main_query)

    if v1_webhook:
        search_query = OpinionDocument.search()
        v1_query, _ = do_es_api_query(
            search_query,
            cd,
            SEARCH_ALERTS_OPINION_HL_FIELDS,
            ALERTS_HL_TAG,
            "v3",
        )
        v1_query = v1_query.extra(
            from_=0,
            size=settings.SCHEDULED_ALERT_HITS_LIMIT,
        )
        multi_search = multi_search.add(v1_query)

    responses = multi_search.execute()
    results = responses[0]
    limit_inner_hits({}, results, cd["type"])
    set_results_highlights(results, cd["type"])
    set_child_docs_and_score(results)
    if v1_webhook:
        v1_results = responses[1]
    return results, v1_results


class Command(VerboseCommand):
    help = (
        "Sends the alert emails on a real time, daily, weekly or monthly "
        "basis."
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.options = {}
        self.valid_ids = []
        self.date_today = date.today()

    def add_arguments(self, parser):
        parser.add_argument(
            "--rate",
            required=True,
            choices=Alert.ALL_FREQUENCIES,
            help=f"The rate to send emails ({', '.join(Alert.ALL_FREQUENCIES)})",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        self.options = options
        if options["rate"] == Alert.REAL_TIME:
            self.remove_stale_rt_items()
            self.valid_ids = self.get_new_ids()

        self.send_emails_and_webhooks(options["rate"])
        if options["rate"] == Alert.REAL_TIME:
            self.clean_rt_queue()

    def run_query(self, alert, rate, v1_webhook=False):
        results = []
        v1_results = None
        logger.info(f"Now running the query: {alert.query}\n")

        # Make a dict from the query string.
        qd = QueryDict(alert.query.encode(), mutable=True)
        try:
            del qd["filed_before"]
        except KeyError:
            pass
        qd["order_by"] = "score desc"
        cut_off_date = get_cut_off_start_date(rate, self.date_today)
        # Default to 'o', if not available, according to the front end.
        query_type = qd.get("type", SEARCH_TYPES.OPINION)
        qd["filed_after"] = cut_off_date
        cut_off_end_date = get_cut_off_end_date(rate, cut_off_date)
        if cut_off_end_date:
            qd["filed_before"] = cut_off_end_date
        if query_type != SEARCH_TYPES.OPINION:
            # This command now only serves OPINION search alerts.
            return query_type, results, v1_results

        logger.info(f"Data sent to SearchForm is: {qd}\n")
        search_form = SearchForm(qd)
        if search_form.is_valid():
            cd = search_form.cleaned_data
            if rate == Alert.REAL_TIME and len(self.valid_ids) == 0:
                # Bail out. No results will be found if no valid_ids.
                return query_type, results, v1_results

            if rate == Alert.REAL_TIME:
                cd.update({"id": " ".join([str(i) for i in self.valid_ids])})
            results, v1_results = query_alerts_es(cd, v1_webhook)

        logger.info(f"There were {len(results)} results.")
        return qd, results, v1_results

    def send_emails_and_webhooks(self, rate):
        """Send out an email and webhook events to every user whose alert has a
        new hit for a rate.
        """
        users = User.objects.filter(alerts__rate=rate).distinct()

        alerts_sent_count = 0
        for user in users:
            alerts = user.alerts.filter(rate=rate)
            logger.info(f"Running alerts for user '{user}': {alerts}")

            # Query user's webhooks.
            user_webhooks = user.webhooks.filter(
                event_type=WebhookEventType.SEARCH_ALERT, enabled=True
            )
            v1_webhook = WebhookVersions.v1 in {
                webhook.version for webhook in user_webhooks
            }
            if rate == Alert.REAL_TIME:
                if not user.profile.is_member:
                    continue

            hits = []
            for alert in alerts:
                try:
                    qd, results, v1_results = self.run_query(
                        alert, rate, v1_webhook
                    )
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
                    hits.append([alert, search_type, results, len(results)])
                    alert.query_run = qd.urlencode()
                    alert.date_last_hit = now()
                    alert.save()

                    # Send webhook event if the user has a SEARCH_ALERT
                    # endpoint enabled.
                    for user_webhook in user_webhooks:
                        results = (
                            v1_results
                            if user_webhook.version == WebhookVersions.v1
                            else results
                        )
                        send_search_alert_webhook(results, user_webhook, alert)

            if len(hits) > 0:
                alerts_sent_count += 1
                send_alert(user.profile, hits)

        async_to_sync(tally_stat)(f"alerts.sent.{rate}", inc=alerts_sent_count)
        logger.info(f"Sent {alerts_sent_count} {rate} email alerts.")

    def clean_rt_queue(self):
        """Clean out any items in the RealTime queue once they've been run or
        if they are stale.
        """
        RealTimeQueue.objects.filter(
            item_type=SEARCH_TYPES.OPINION, item_pk__in=self.valid_ids
        ).delete()

    def remove_stale_rt_items(self, age=2):
        """Remove anything old from the RTQ.

        :param age: How many days old should items be before we start deleting
        them?
        """
        RealTimeQueue.objects.filter(
            date_modified__lt=now() - timedelta(days=age),
        ).delete()

    def get_new_ids(self):
        """Get an intersection of the items that are new in the DB and those
        that have made it into ES.

        For every item that's in the RealTimeQueue, query ES and see which
        have made it to the index. We'll use these to run the alerts.

        Returns a list like so: [list, of, ids]
        """
        ids = RealTimeQueue.objects.filter(item_type=SEARCH_TYPES.OPINION)
        if not ids.exists():
            return []
        # Get valid RT IDs from ES.
        search_query = OpinionDocument.search()
        ids_query = ES_Q("terms", id=[str(i.item_pk) for i in ids])
        s = search_query.query(ids_query)
        s = s.source(includes=["id"])
        s = s.extra(
            from_=0,
            size=MAX_RT_ITEM_QUERY,
        )
        results = s.execute()
        return [int(r["id"]) for r in results]
