# -*- coding: utf-8 -*-
from juriscraper.lib import importer
from operator import itemgetter
from django.utils.timezone import now

from cl.scrapers.models import ErrorLog
from cl.search.models import Court, OpinionCluster
from datetime import date, timedelta
from django.conf import settings
from django.core import mail
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand
from django.template import loader
from django.db.models import Count


def _make_query_dict(query_list):
    """Reformat the results into dicts.
    """
    result_dict = {}
    for item in query_list:
        result_dict[item['pk']] = item['count']
    return result_dict


def calculate_counts():
    """Grab the information for new documents over the past 30 days, and
    calculate the number of cases found for each court.

    Returns a list like so:
    [('ca1', date1, link), ('ca2', date2, link), ('ca3',...)]
    """
    thirty_days_ago = now() - timedelta(days=30)
    thirty_five_days_ago = now() - timedelta(days=35)
    cts_more_than_30_days = Court.objects \
        .filter(docket__clusters__date_filed__gt=thirty_days_ago) \
        .annotate(count=Count('docket__clusters__sub_opinions__pk')) \
        .values('pk', 'count')

    # Needed because annotation calls above don't return courts with no new
    # opinions
    all_active_courts = Court.objects.filter(has_opinion_scraper=True) \
        .values_list('pk', flat=True).order_by('position')

    # Reformat the results into dicts...
    cts_more_than_30_days = _make_query_dict(cts_more_than_30_days)

    # Combine everything
    most_recent_opinions = []
    recently_dying_courts = []
    mod_list = importer.build_module_list('juriscraper.opinions')
    mod_dict = {}
    for v in mod_list:
        court = v.rsplit('.')[-1]
        mod_dict[court] = v

    for court in all_active_courts:
        if cts_more_than_30_days.get(court, 0) == 0:
            # No results in newer than 35 days. Get date of most recent
            # item.
            date_filed = OpinionCluster.objects.filter(
                docket__court_id=court
            ).order_by(
                '-date_filed'
            )[0].date_filed
            try:
                mod = __import__(
                    mod_dict[court],
                    globals(),
                    locals(),
                    [mod_dict[court].rsplit('.')[0]],
                )
                url = mod.Site().url
                method = mod.Site().method
            except KeyError:
                # Happens when multiple scrapers for single court.
                url = ""
                method = "Unknown"
            if thirty_five_days_ago.date() < date_filed < \
                    thirty_days_ago.date():
                recently_dying_courts.append(
                    (court, date_filed, method, url)
                )
            most_recent_opinions.append(
                (court, date_filed, method, url)
            )

    # Sort by date (index 1)
    most_recent_opinions.sort(key=itemgetter(1), reverse=True)

    return most_recent_opinions, recently_dying_courts


def send_report(report, subject, debug=True):
    """Send the report to the admins"""
    if debug:
        BACKEND = 'django.core.mail.backends.console.EmailBackend'
    else:
        BACKEND = settings.EMAIL_BACKEND

    connection = mail.get_connection(backend=BACKEND)
    connection.open()
    msg = EmailMessage(subject, report, settings.SERVER_EMAIL,
                       [a[1] for a in settings.ADMINS],
                       connection=connection)
    # Set it to html only -- making a plaintext version would be awful.
    msg.content_subtype = 'html'
    msg.send()
    connection.close()


def tally_errors():
    """Look at the error db and gather the latest errors from it"""
    yesterday = now() - timedelta(days=1)
    cts_critical = Court.objects \
        .filter(errorlog__log_time__gt=yesterday,
                errorlog__log_level="CRITICAL") \
        .annotate(count=Count('errorlog__pk')) \
        .values('pk', 'count')
    cts_warnings = Court.objects \
        .filter(errorlog__log_time__gt=yesterday,
                errorlog__log_level="WARNING") \
        .annotate(count=Count('errorlog__pk')) \
        .values('pk', 'count')

    all_active_courts = Court.objects.filter(in_use=True).values(
        'pk').order_by('position')

    # Reformat as dicts...
    cts_critical = _make_query_dict(cts_critical)
    cts_warnings = _make_query_dict(cts_warnings)

    # Make a union of the dicts
    errors = {}
    for court in all_active_courts:
        critical_count = cts_critical.get(court['pk'], 0)
        warning_count = cts_warnings.get(court['pk'], 0)
        if critical_count + warning_count == 0:
            # No issues, move along.
            continue
        errors[court['pk']] = [critical_count, warning_count]

    return errors


def generate_report():
    """Look at the counts and errors, generate and return a report.

    """
    most_recent_opinions, recently_dying_courts = calculate_counts()
    errors = tally_errors()

    html_template = loader.get_template('report.html')
    context = {
        'most_recent_opinions': most_recent_opinions,
        'recently_dying_courts': recently_dying_courts,
        'errors': errors,
    }
    report = html_template.render(context)

    subject = 'CourtListener status email for {date}'.format(
        date=date.strftime(now(), '%Y-%m-%d')
    )

    return report, subject


def truncate_database_logs():
    """Truncate the database so that it doesn't grow forever."""
    thirty_days_ago = now() - timedelta(days=30)
    ErrorLog.objects.filter(log_time__lt=thirty_days_ago).delete()


class Command(BaseCommand):
    help = 'Generates a report and sends it to the administrators.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--debug',
            action='store_true',
            dest='debug',
            default=False,
            help='Run the command, but take no action. Be verbose and send '
                 'email to the console.'
        )

    def handle(self, *args, **options):
        report, subject = generate_report()
        send_report(report, subject, options['debug'])
        truncate_database_logs()
