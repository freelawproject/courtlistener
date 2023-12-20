from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from cl.donate.models import NeonWebhookEvent


@receiver(
    post_save,
    sender=NeonWebhookEvent,
    dispatch_uid="truncate_webhook_events",
)
def truncate_webhook_events(sender, instance=None, created=False, **kwargs):
    if not instance.id % settings.NEON_MAX_WEBHOOK_NUMBER:
        NeonWebhookEvent.objects.filter(
            pk__lte=instance.id - settings.NEON_MAX_WEBHOOK_NUMBER
        ).delete()
