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
        if not events.exists():
            return

        # Filter out v4 API-related user milestones since those are now handled
        # by the Zoho integration. We keep:
        #  - Global events (no user)
        #  - Any webhook events
        #  - Any v3 API events (global or user milestones)
        def should_include(event: Event) -> bool:
            desc = event.description.lower()
            return event.user is None or "webhook" in desc or "v3" in desc

        events_for_email = [e for e in events if should_include(e)]

        if not events_for_email:
            return

        template = loader.get_template("emails/events_email.txt")
        send_mail(
            subject=f"CourtListener events email for {today.date().isoformat()}",
            message=template.render({"events": events_for_email}),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[settings.PARTNERSHIP_EMAIL_ADDRESS],
        )
