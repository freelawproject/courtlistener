from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand
from django.db.models import Sum
from django.template import loader, Context
from optparse import make_option
from alert.search.models import Document, Court
from alert.stats import Stat
from alert.userHandling.models import UserProfile
from datetime import date
from datetime import timedelta


class Command(BaseCommand):
    option_list = BaseCommand.option_list + (
        make_option(
            '--simulate',
            action='store_true',
            default=False,
            help='Run the command in simulation mode, not sending any emails'
        ),

    )
    help = 'Sends the annual reminders to people that donated and wanted a reminder.'

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
            up.user.email,
        )
        msg.attach_alternative(html, 'text/html')
        msg.send(fail_silently=False)

        if up.user.first_name:
            hello_line = "Hello %s," % up.user.first_name
        else:
            hello_line = "Hello,"
        email_body = (
            "%s\n\n"
            "About a year ago you donated $%02f to the Free Law Project to support our work on the CourtListener "
            "platform and other projects under our umbrella. We've had a fantastic year and we hope you'll donate "
            "again to help sustain our work. To do so, please click the link below.\n\n"
            " - https://www.courtlistener.com/donate/\n\n"
            "With your support, we've made a lot of progress over the past year:\n\n"
            " - We've added %s opinions to our collection.\n"
            " - We now have %s jurisdictions that can be queried or analyzed in our bulk data files.\n"
            " - We've served our bulk data files %s times.\n"
            " - We've sent %s email alerts.\n"
            " - We've added a bunch of new features too numerous to mention.\n\n"
            "We still have a lot to do, but every bit that you give helps to sustain our efforts to create a free "
            "and open legal ecosystem in America. If you're interested in what we have planned, you can always take a "
            "look at our planning board and even get involved, suggesting ideas or prioritization. For ideas about "
            "how to get involved, see our page at:\n\n"
            " - https://www.courtlistener.com/contribute/\n\n"
            "Since it's been a year, we hope that you will consider donating to the Free Law Project again, and that"
            "you will consider telling your friends and colleagues about the work we do.\n\n"
            "If you have any questions, please don't hesitate to get in touch.\n\n"
            "Mike and Brian\n"
            "Creators\n"
            "Free Law Project\n"
            "donate@freelawproject.org\n")

    def handle(self, *args, **options):
        self.verbosity = int(options.get('verbosity', 1))

        if options['simulate']:
            self.stdout.write("**********************************")
            self.stdout.write("* SIMULATE MODE - NO EMAILS SENT *")
            self.stdout.write("**********************************")

        about_a_year_ago = date.today() - timedelta(days=355)
        ups = UserProfile.objects.filter(
            donation__date_created__year=about_a_year_ago.year,
            donation__date_created__month=about_a_year_ago.month,
            donation__date_created_day=about_a_year_ago.day,
            donation__send_annual_reminder=True,
        )
        # Gather some stats to email
        self.new_doc_count = Document.objects.filter(time_retreived__gte=about_a_year_ago).count()
        self.court_count = Court.objects.all().count()
        self.bulk_data_count = Stat.objects.filter(
            name__startswith='bulk_data',
            date_logged__gte=about_a_year_ago
        ).aggregate(Sum('count'))['count__sum']
        self.alerts_sent_count = Stat.objects.filter(
            name='alerts.sent',
            date_logged__gte=about_a_year_ago,
        ).aggregate(Sum('count'))['count__sum']
        for up in ups:
            # Iterate over the people and send them emails
            if not options['simulate']:
                self.send_reminder_email(up, donation.amount)
