from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.template import loader
from django.utils.timezone import now

from cl.stats.models import Event
from cl.lib.command_utils import VerboseCommand


class Command(VerboseCommand):
    help = "Send an email to the admins with any events from the past day."

    def handle(self, *args, **options) -> None:
        super(Command, self).handle(*args, **options)
        today = now()
        yesterday = today - timedelta(days=1)
        events = Event.objects.filter(date_created__gte=yesterday)
        if events.count() > 0:
            template = loader.get_template("emails/events_email.txt")
            send_mail(
                subject="CourtListener events email for %s"
                % today.date().isoformat(),
                message=template.render({"events": events}),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=settings.MANAGERS,
            )
