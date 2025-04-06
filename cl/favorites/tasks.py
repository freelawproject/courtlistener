from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.utils.timezone import now

from juriscraper.lib.exceptions import PacerLoginException
from juriscraper.pacer import DownloadConfirmationPage
from redis import ConnectionError as RedisConnectionError

from cl.celery_init import app
from cl.lib.pacer_session import ProxyPacerSession, get_or_cache_pacer_cookies
from cl.search.models import RECAPDocument
from .models import PrayerAvailability
from .utils import prayer_unavailable


@app.task(
    bind=True,
    autoretry_for=(RedisConnectionError, PacerLoginException),
    max_retries=5,
    interval_start=5,
    interval_step=5,
    ignore_result=True,
)
@transaction.atomic
def check_prayer_pacer(rd: RECAPDocument, user_pk: int) -> bool:
    """Helper function for should_check_prayer_availability().
    :param rd: The RECAPDocument of interest
    :param user_pk: The primary key of the user who requested the document
    :return: bool that indicates whether document is available
    """
    court_id = rd.docket_entry.docket.court.pk
    pacer_doc_id = rd.pacer_doc_id

    recap_user = User.objects.get(username="recap")
    session_data = get_or_cache_pacer_cookies(
        recap_user.pk, settings.PACER_USERNAME, settings.PACER_PASSWORD
    )
    s = ProxyPacerSession(
        cookies=session_data.cookies, proxy=session_data.proxy_address
    )
    receipt_report = DownloadConfirmationPage(court_id, s)
    receipt_report.query(pacer_doc_id)
    data = receipt_report.data

    if data == {}:
        rd.is_sealed = True
        rd.save()
        PrayerAvailability.objects.update_or_create(
            recap_document=rd, defaults={"last_checked": now}
        )
        prayer_unavailable(rd, user_pk)
        return
    else:
        # making sure that previously sealed documents that are now available are marked as such
        rd.is_sealed = False
        rd.save()
        PrayerAvailability.objects.filter(recap_document=rd).delete()

    if data.billable_pages != 30:
        rd.page_count = data.billable_pages
        rd.save()