from datetime import timedelta

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.timezone import now

from .models import Prayer, PrayerAvailability
from .tasks import check_prayer_pacer
from .utils import prayer_unavailable


@receiver(
    post_save,
    sender=Prayer,
    dispatch_uid="check_prayer_availability",
)
def check_prayer_availability(sender, instance: Prayer, **kwargs):
    """
    Signal to check if a given RecapDocument is available for purchase after a user has requested it
    as part of the pray-and-pay project.
    """

    rd = instance.recap_document
    user = instance.user

    pacer_doc_id = rd.pacer_doc_id

    if pacer_doc_id == "":
        PrayerAvailability.objects.update_or_create(
            recap_document=rd, defaults={"last_checked": now}
        )

        prayer_unavailable(rd, user.pk)
        return

    # stopping the check early to prevent us from repeatedly crawling PACER to confirm an available document still remains available
    if rd.is_sealed == False:
        return

    try:
        document_availability = PrayerAvailability.objects.get(
            recap_document=rd
        )
    except PrayerAvailability.DoesNotExist:
        check_prayer_pacer.delay(rd.pk, user.pk)
        return

    if document_availability.last_checked >= (now() - timedelta(weeks=1)):
        prayer_unavailable(rd, user.pk)
    else:
        check_prayer_pacer.delay(rd.pk, user.pk)
