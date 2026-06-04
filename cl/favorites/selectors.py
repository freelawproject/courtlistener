from datetime import timedelta

from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone

from cl.favorites.models import Prayer


async def prayer_eligible(user: User) -> tuple[bool, int]:
    allowed_prayer_count = settings.ALLOWED_PRAYER_COUNT

    @sync_to_async
    def is_FLP_member():
        return user.profile.is_member

    if await is_FLP_member():
        allowed_prayer_count *= 3

    now = timezone.now()
    last_24_hours = now - timedelta(hours=24)

    # Count the number of prayers made by this user in the last 24 hours
    prayer_count = await Prayer.objects.filter(
        user=user, date_created__gte=last_24_hours
    ).acount()

    return prayer_count < allowed_prayer_count, (
        allowed_prayer_count - prayer_count
    )
