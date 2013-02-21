# -*- coding: utf-8 -*-

from alert.scrapers.models import ErrorLog
from alert.search.models import Court
from datetime import date, timedelta
from django.conf import settings
from django.core import mail
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand
from django.template import loader, Context
from django.db.models import Count
from optparse import make_option


class Command(BaseCommand):
    option_list = BaseCommand.option_list + (
        make_option('--debug',
            action='store_true',
            dest='debug',
            default=False,
            help='Run the command, but take no action. Be verbose and send '
                 'email to the console.'),
        )
    args = '[--debug]'
    help = 'Generates a report and sends it to the administrators.'

    def _num_weekdays(self, start_date, end_date=date.today()):
        '''Calculates the number of weekdays between start_date and end_date

        From: http://stackoverflow.com/questions/3615375/
        '''
        daygenerator = (start_date + timedelta(x + 1) for x in
                        xrange((end_date - start_date).days))
        return sum(1 for day in daygenerator if day.weekday() < 5)

    def _make_query_dict(self, query_list):
        '''Reformat the results into dicts.
        '''
        result_dict = {}
        for item in query_list:
            result_dict[item['pk']] = item['count']
        return result_dict

    def _calculate_averages(self):
        '''Grab the information for new documents over the past 30 days, and
        calculate the average number of cases found for each court.

        Returns a dict like so:
        {'ca1':['40','42', '39'], 'ca2': ['23', '23', '0'], 'ca3':...}

        Note that the values in the list are:
         0: The average for the past 30 days.
         1: The average for the past 7 days.
         2: The count for today
        '''
        last_day = date.today() - timedelta(days=1)
        seven_days_ago = date.today() - timedelta(days=7)
        thirty_days_ago = date.today() - timedelta(days=30)

        # This makes a mess of queries, but gets everything we need.
        cts_last_day = Court.objects\
                            .filter(document__dateFiled__gt=last_day)\
                            .annotate(count=Count('document__pk'))\
                            .values('pk', 'count')
        cts_seven_days = Court.objects\
                              .filter(document__dateFiled__gt=seven_days_ago)\
                              .annotate(count=Count('document__pk'))\
                              .values('pk', 'count')
        cts_thirty_days = Court.objects\
                               .filter(document__dateFiled__gt=thirty_days_ago)\
                               .annotate(count=Count('document__pk'))\
                               .values('pk', 'count')

        # Needed because annotation calls above don't return courts with no new
        # opinions
        all_active_courts = Court.objects.filter(in_use=True).values('pk')

        # Reformat the results into dicts...
        cts_last_day = self._make_query_dict(cts_last_day)
        cts_seven_days = self._make_query_dict(cts_seven_days)
        cts_thirty_days = self._make_query_dict(cts_thirty_days)

        # Combine everything and make it into pretty results.
        averages = {}
        totals = ['TOTAL', 0, 0, 0]
        for court in all_active_courts:
            thirty = cts_thirty_days.get(court['pk'], 0)
            seven = cts_seven_days.get(court['pk'], 0)
            last = cts_last_day.get(court['pk'], 0)
            totals[1] += thirty
            totals[2] += seven
            totals[3] += last
            averages[court['pk']] = [thirty, seven, last]

        # Stringify the values...
        for i in range(1, 4):
            totals[i] = '%.2f' % totals[i]

        # Determine if any court has zero results for the past seven days, but
        # not for the past 30. That's usually a critical problem.
        critical_counts = False
        for court in all_active_courts:
            last_thirty_day_count = cts_thirty_days.get(court['pk'], 0)
            last_seven_day_count = cts_seven_days.get(court['pk'], 0)
            if last_seven_day_count == 0 and last_thirty_day_count > 0:
                critical_counts = True
                break

        return averages, totals, critical_counts

    def generate_report(self):
        '''Look at the errors for the day, generate and return a report.

        '''
        yesterday = date.today() - timedelta(days=1)
        cts_critical = Court.objects\
                            .filter(errorlog__log_time__gt=yesterday,
                                    errorlog__log_level="CRITICAL")\
                            .annotate(count=Count('errorlog__pk'))\
                            .values('pk', 'count')
        cts_warnings = Court.objects\
                            .filter(errorlog__log_time__gt=yesterday,
                                    errorlog__log_level="WARNING")\
                            .annotate(count=Count('errorlog__pk'))\
                            .values('pk', 'count')

        all_active_courts = Court.objects.filter(in_use=True).values('pk')

        # Reformat as dicts...
        cts_critical = self._make_query_dict(cts_critical)
        cts_warnings = self._make_query_dict(cts_warnings)

        # Make a union of the dicts
        errors = {}
        for court in all_active_courts:
            critical_count = cts_critical.get(court['pk'], 0)
            warning_count = cts_warnings.get(court['pk'], 0)
            errors[court['pk']] = [critical_count, warning_count]

        averages, totals, critical_counts = self._calculate_averages()

        # Make the report!
        html_template = loader.get_template('scrapers/report.html')
        c = Context({'averages': averages, 'totals': totals, 'errors': errors})
        report = html_template.render(c)

        # Sort out if the subject is critical, and add a date to it
        subject = 'CourtListener status email for %s' % \
                                    date.strftime(date.today(), '%Y-%m-%d')
        if critical_counts or cts_critical:
            subject = '*CRITICAL* - ' + subject

        return report, subject

    def send_report(self, report, subject, debug=False):
        '''Send the report to the admins'''
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

    def truncate_database_logs(self):
        '''Truncate the database so that it doesn't grow forever.'''
        thirty_days_ago = date.today() - timedelta(days=30)
        ErrorLog.objects.filter(log_time__lt=thirty_days_ago).delete()

    def handle(self, *args, **options):
        self.verbosity = int(options.get('verbosity', 1))
        self.debug = options.get('debug')
        report, subject = self.generate_report()

        # Send the email
        self.send_report(report, subject, self.debug)

        # Clear old logs from the database
        self.truncate_database_logs()
