from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import (
    Avg,
    Count,
    ExpressionWrapper,
    F,
    FloatField,
    Q,
    Subquery,
)
from django.db.models.functions import Cast, Extract, Now, Sqrt
from django.utils import timezone

from cl.favorites.models import Prayer
from cl.search.models import RECAPDocument


async def prayer_eligible(user: User) -> bool:
    allowed_prayer_count = settings.ALLOWED_PRAYER_COUNT

    now = timezone.now()
    last_24_hours = now - timedelta(hours=24)

    # Count the number of prayers made by this user in the last 24 hours
    prayer_count = await Prayer.objects.filter(
        user=user, date_created__gte=last_24_hours
    ).acount()

    return prayer_count < allowed_prayer_count


async def create_prayer(
    user: User, recap_document: RECAPDocument
) -> Prayer | None:
    if await prayer_eligible(user) and not recap_document.is_available:
        new_prayer, created = await Prayer.objects.aget_or_create(
            user=user, recap_document=recap_document
        )
        return new_prayer if created else None
    return None


async def get_top_prayers() -> list[RECAPDocument]:
    # Calculate the age of each prayer
    prayer_age = ExpressionWrapper(
        Extract(Now() - F("prayers__date_created"), "epoch"),
        output_field=FloatField(),
    )
    waiting_prayers = Prayer.objects.filter(status=Prayer.WAITING).values(
        "recap_document_id"
    )
    # Annotate each RECAPDocument with the number of prayers and the average prayer age
    documents = (
        RECAPDocument.objects.filter(id__in=Subquery(waiting_prayers))
        .select_related(
            "docket_entry",
            "docket_entry__docket",
            "docket_entry__docket__court",
        )
        .only(
            "pk",
            "document_type",
            "document_number",
            "attachment_number",
            "pacer_doc_id",
            "description",
            "docket_entry__docket_id",
            "docket_entry__docket__slug",
            "docket_entry__docket__pacer_case_id",
            "docket_entry__docket__court__jurisdiction",
            "docket_entry__docket__court_id",
        )
        .annotate(
            prayer_count=Count(
                "prayers", filter=Q(prayers__status=Prayer.WAITING)
            ),
            avg_prayer_age=Avg(
                prayer_age, filter=Q(prayers__status=Prayer.WAITING)
            ),
        )
        .annotate(
            geometric_mean=Sqrt(
                Cast(
                    F("prayer_count")
                    * Cast(F("avg_prayer_age"), FloatField()),
                    FloatField(),
                )
            )
        )
        .order_by("-geometric_mean")[:50]
    )
    return [doc async for doc in documents.aiterator()]
