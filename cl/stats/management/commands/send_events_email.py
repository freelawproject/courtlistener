from datetime import timedelta

from django.core.mail import mail_admins
from django.core.management.base import BaseCommand
from django.template import loader
from django.utils.timezone import now

from cl.stats.models import Event


class Command(BaseCommand):
    help = 'Send an email to the admins with any events from the past day.'

    def handle(self, *args, **options):
        today = now()
        yesterday = today - timedelta(days=1)
        events = Event.objects.filter(date_created__gte=yesterday)
        if events.count() > 0:
            template = loader.get_template('emails/events_email.txt')
            txt = template.render({'events': events})
            mail_admins(
                'CourtListener events email for %s' % today.date().isoformat(),
                txt,
            )
