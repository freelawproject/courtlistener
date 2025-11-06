from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.template import loader
from django.utils.timezone import now

from cl.lib.command_utils import VerboseCommand
from cl.stats.models import Event


class Command(VerboseCommand):
    help = """Send an email to partnership managers with usage statistics"""

    def handle(self, *args, **options) -> None:
        super().handle(*args, **options)
        today = now()
        yesterday = today - timedelta(days=1)
        events = Event.objects.filter(date_created__gte=yesterday)
        if not events.count():
            return

        # Filter out API-related user milestones since those are now handled by
        # the Zoho integration. This keeps only global API events, global
        # webhook events, and user tracking webhook milestones.
        events_for_email = [
            e
            for e in events.all()
            if not e.user or "webhook" in e.description.lower()
        ]
        template = loader.get_template("emails/events_email.txt")
        send_mail(
            subject=f"CourtListener events email for {today.date().isoformat()}",
            message=template.render({"events": events_for_email}),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[settings.PARTNERSHIP_EMAIL_ADDRESS],
        )
