from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand
from django.db.models import Sum
from django.template import loader, Context
from optparse import make_option
from django.utils.timezone import now
from alert.search.models import Document, Court
from alert.stats import Stat
from alert.userHandling.models import UserProfile
from datetime import date
from datetime import timedelta


class Command(BaseCommand):
    help = 'Sends the annual reminders to people that donated and wanted a reminder.'

    def gather_stats_and_ups(self):
        about_a_year_ago = now() - timedelta(days=355)

        # Gather some stats to email
        self.new_doc_count = Document.objects.filter(time_retrieved__gte=about_a_year_ago).count()
        self.court_count = Court.objects.all().count()
        self.bulk_data_count = Stat.objects.filter(
            name__startswith='bulk_data',
            date_logged__gte=about_a_year_ago
        ).aggregate(Sum('count'))['count__sum']
        self.alerts_sent_count = Stat.objects.filter(
            name='alerts.sent',
            date_logged__gte=about_a_year_ago,
        ).aggregate(Sum('count'))['count__sum']

        self.ups = UserProfile.objects.filter(
            donation__date_created__year=about_a_year_ago.year,
            donation__date_created__month=about_a_year_ago.month,
            donation__date_created__day=about_a_year_ago.day,
            donation__send_annual_reminder=True,
            donation__status=4
        ).annotate(Sum('donation__amount'))

    def send_reminder_email(self, up, amount):
        """Send an email imploring the person for another donation."""
        email_subject = "Please donate again to the Free Law Project"
        email_sender = "CourtListener <mike@courtlistener.com>"
        txt_template = loader.get_template('donate/reminder_email.txt')
        html_template = loader.get_template('donate/reminder_email.html')
        c = Context({
            'amount': amount,
            'new_doc_count': self.new_doc_count,
            'bulk_data_count': self.bulk_data_count,
            'alerts_sent_count': self.alerts_sent_count,
            'court_count': self.court_count
        })
        txt = txt_template.render(c)
        html = html_template.render(c)
        msg = EmailMultiAlternatives(
            email_subject,
            txt,
            email_sender,
            [up.user.email],
        )
        msg.attach_alternative(html, 'text/html')
        msg.send(fail_silently=False)

    def handle(self, *args, **options):
        self.verbosity = int(options.get('verbosity', 1))
        self.gather_stats_and_ups()
        for up in self.ups:
            # Iterate over the people and send them emails
            self.send_reminder_email(up, up.donation__amount__sum)
