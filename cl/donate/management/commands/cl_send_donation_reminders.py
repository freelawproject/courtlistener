from datetime import timedelta
from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand
from django.db.models import Sum
from django.template import loader
from django.utils.timezone import now
from cl.search.models import Opinion, Court
from cl.stats import Stat


class Command(BaseCommand):
    help = ('Sends the annual reminders to people that donated and wanted a '
            'reminder.')

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)
        self.new_doc_count = 0
        self.court_count = 0
        self.bulk_data_count = 0
        self.alerts_sent_count = 0
        self.users = []
        self.verbosity = 0

    def gather_stats_and_users(self):
        about_a_year_ago = now() - timedelta(days=355)

        # Gather some stats to email
        self.new_doc_count = Opinion.objects.filter(
            date_created__gte=about_a_year_ago
        ).count()
        self.court_count = Court.objects.all().count()
        self.bulk_data_count = Stat.objects.filter(
            name__startswith='bulk_data',
            date_logged__gte=about_a_year_ago
        ).aggregate(Sum('count'))['count__sum']
        self.alerts_sent_count = Stat.objects.filter(
            name='alerts.sent',
            date_logged__gte=about_a_year_ago,
        ).aggregate(Sum('count'))['count__sum']
        self.users = User.objects.filter(
            donations__date_created__year=about_a_year_ago.year,
            donations__date_created__month=about_a_year_ago.month,
            donations__date_created__day=about_a_year_ago.day,
            donations__send_annual_reminder=True,
            donations__status=4
        ).annotate(Sum('donations__amount'))

    def send_reminder_email(self, user, amount):
        """Send an email imploring the person for another donation."""
        email_subject = "Please donate again to Free Law Project"
        email_sender = "CourtListener <mike@courtlistener.com>"
        txt_template = loader.get_template('reminder_email.txt')
        html_template = loader.get_template('reminder_email.html')
        context = {
            'amount': amount,
            'new_doc_count': self.new_doc_count,
            'bulk_data_count': self.bulk_data_count,
            'alerts_sent_count': self.alerts_sent_count,
            'court_count': self.court_count
        }
        txt = txt_template.render(context)
        html = html_template.render(context)
        msg = EmailMultiAlternatives(
            email_subject,
            txt,
            email_sender,
            [user.email],
        )
        msg.attach_alternative(html, 'text/html')
        msg.send(fail_silently=False)

    def handle(self, *args, **options):
        self.verbosity = int(options.get('verbosity', 1))
        self.gather_stats_and_users()
        for user in self.users:
            # Iterate over the people and send them emails
            self.send_reminder_email(user, user.donations__amount__sum)
