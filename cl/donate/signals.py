from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.timezone import now

from cl.donate.models import NeonWebhookEvent


@receiver(
    post_save,
    sender=NeonWebhookEvent,
    dispatch_uid="truncate_webhook_events",
)
def truncate_webhook_events(sender, instance=None, created=False, **kwargs):
    if not instance.id % settings.NEON_MAX_WEBHOOK_NUMBER:
        about_twelve_weeks_ago = now() - timedelta(days=12 * 7)
        NeonWebhookEvent.objects.filter(
            Q(pk__lte=instance.id - settings.NEON_MAX_WEBHOOK_NUMBER)
            | Q(date_created__lt=about_twelve_weeks_ago)
        ).delete()
