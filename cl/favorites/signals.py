from datetime import datetime

from django.conf import settings
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
def check_prayer_availability( 
     sender, instance: Prayer, **kwargs 
): 
    """ 
    Right now, this receiver exists to enqueue the task to parse RECAPDocuments for caselaw citations. 
    More functionality can be put here later. There may be things currently in the save function 
    of RECAPDocument that would be better placed here for reasons of maintainability and testability. 
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

    try:
        document_availability = PrayerAvailability.objects.get(
            recap_document=rd
        )
    except PrayerAvailability.DoesNotExist:
        check_prayer_pacer.delay(rd, user.pk)
        return
    
    if document_availability.last_checked >= (
        now - datetime.timedelta(weeks=1)
    ):
        prayer_unavailable(rd, user.pk)
    else:
        check_prayer_pacer.delay(rd, user.pk)
