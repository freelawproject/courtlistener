from datetime import date, timedelta
from operator import itemgetter

import pkg_resources
from django.conf import settings
from django.core import mail
from django.core.mail import EmailMessage
from django.db.models import Count
from django.template import loader
from django.utils.timezone import now
from juriscraper.lib import importer

from cl.lib.command_utils import VerboseCommand
from cl.search.models import Court, OpinionCluster


def _make_query_dict(query_list) -> dict:
    """Reformat the results into dicts."""
    return {item["pk"]: item["count"] for item in query_list}


def calculate_counts():
    """Grab the information for new documents over the past 30 days, and
    calculate the number of cases found for each court.

    Returns a list like so:
    [('ca1', date1, link), ('ca2', date2, link), ('ca3',...)]
    """
    thirty_days_ago = now() - timedelta(days=30)
    thirty_five_days_ago = now() - timedelta(days=35)
    cts_more_than_30_days = (
        Court.objects.filter(dockets__clusters__date_filed__gt=thirty_days_ago)
        .annotate(count=Count("dockets__clusters__sub_opinions__pk"))
        .values("pk", "count")
    )

    # Needed because annotation calls above don't return courts with no new
    # opinions
    all_active_courts = (
        Court.objects.filter(has_opinion_scraper=True)
        .values_list("pk", flat=True)
        .order_by("position")
    )

    # Reformat the results into dicts...
    cts_more_than_30_days = _make_query_dict(cts_more_than_30_days)

    # Combine everything
    most_recent_opinions = []
    recently_dying_courts = []
    mod_list = importer.build_module_list("juriscraper.opinions")
    mod_dict = {}
    for v in mod_list:
        court = v.rsplit(".")[-1]
        mod_dict[court] = v

    for court in all_active_courts:
        if cts_more_than_30_days.get(court, 0) == 0:
            # No results in newer than 35 days. Get date of most recent
            # item.
            try:
                date_filed = (
                    OpinionCluster.objects.filter(docket__court_id=court)
                    .latest("date_filed")
                    .date_filed
                )
            except OpinionCluster.DoesNotExist:
                # New jurisdiction without any results. Punt.
                continue
            try:
                mod = __import__(
                    mod_dict[court],
                    globals(),
                    locals(),
                    [mod_dict[court].rsplit(".")[0]],
                )
                url = mod.Site().url
                method = mod.Site().method
            except KeyError:
                # Happens when multiple scrapers for single court.
                url = ""
                method = "Unknown"
            if (
                thirty_five_days_ago.date()
                < date_filed
                < thirty_days_ago.date()
            ):
                recently_dying_courts.append((court, date_filed, method, url))
            most_recent_opinions.append((court, date_filed, method, url))

    # Sort by date (index 1)
    most_recent_opinions.sort(key=itemgetter(1), reverse=True)

    return most_recent_opinions, recently_dying_courts


def send_report(report, subject, debug=True):
    """Send the report to the admins"""
    if debug:
        BACKEND = "django.core.mail.backends.console.EmailBackend"
    else:
        BACKEND = settings.EMAIL_BACKEND

    connection = mail.get_connection(backend=BACKEND)
    connection.open()
    msg = EmailMessage(
        subject,
        report,
        settings.SERVER_EMAIL,
        [a[1] for a in settings.SCRAPER_ADMINS],
        connection=connection,
    )
    # Set it to html only -- making a plaintext version would be awful.
    msg.content_subtype = "html"
    msg.send()
    connection.close()


def generate_report():
    """Look at the counts and errors, generate and return a report."""
    most_recent_opinions, recently_dying_courts = calculate_counts()
    js_version = pkg_resources.get_distribution("juriscraper").version

    html_template = loader.get_template("report.html")
    context = {
        "most_recent_opinions": most_recent_opinions,
        "recently_dying_courts": recently_dying_courts,
        "errors": {"court": 0},
        "js_version": js_version,
    }
    report = html_template.render(context)

    subject = (
        "[juriscraper-notification] CourtListener status email for "
        "{date}".format(date=date.strftime(now(), "%Y-%m-%d"))
    )

    return report, subject


class Command(VerboseCommand):
    help = "Generates a report and sends it to the administrators."

    def add_arguments(self, parser):
        parser.add_argument(
            "--debug",
            action="store_true",
            dest="debug",
            default=False,
            help="Run the command, but take no action. Be verbose and send "
            "email to the console.",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        report, subject = generate_report()
        send_report(report, subject, options["debug"])
