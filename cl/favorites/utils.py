from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db.models import (
    Avg,
    Case,
    Count,
    ExpressionWrapper,
    F,
    FloatField,
    Q,
    QuerySet,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Cast, Extract, Least, Now, Sqrt
from django.template import loader
from django.utils import timezone

from cl.custom_filters.templatetags.pacer import price
from cl.favorites.models import Prayer
from cl.search.models import RECAPDocument


async def prayer_eligible(user: User) -> tuple[bool, int]:
    allowed_prayer_count = settings.ALLOWED_PRAYER_COUNT

    now = timezone.now()
    last_24_hours = now - timedelta(hours=24)

    # Count the number of prayers made by this user in the last 24 hours
    prayer_count = await Prayer.objects.filter(
        user=user, date_created__gte=last_24_hours
    ).acount()

    return prayer_count < allowed_prayer_count, (
        allowed_prayer_count - prayer_count
    )


async def create_prayer(
    user: User, recap_document: RECAPDocument
) -> Prayer | None:
    if (await prayer_eligible(user))[0] and not recap_document.is_available:
        new_prayer, created = await Prayer.objects.aget_or_create(
            user=user, recap_document=recap_document
        )
        return new_prayer if created else None
    return None


async def delete_prayer(user: User, recap_document: RECAPDocument) -> bool:
    deleted, _ = await Prayer.objects.filter(
        user=user, recap_document=recap_document, status=Prayer.WAITING
    ).adelete()

    return deleted > 0


async def get_prayer_counts_in_bulk(
    recap_documents: list[RECAPDocument],
) -> dict[str, int]:
    """Retrieve the count of prayers with a status of "WAITING" for a list of recap documents.

    :param recap_documents: A list of RECAPDocument instances to filter prayers.
    :return: A dictionary where keys are RECAPDocument IDs and values are the
    count of "WAITING" prayers for each document.
    """

    prayer_counts = (
        Prayer.objects.filter(
            recap_document__in=recap_documents, status=Prayer.WAITING
        )
        .values("recap_document")
        .annotate(count=Count("id"))
    )
    return {
        prayer_count["recap_document"]: prayer_count["count"]
        async for prayer_count in prayer_counts
    }


async def get_existing_prayers_in_bulk(
    user: User, recap_documents: list[RECAPDocument]
) -> dict[int, bool]:
    """Check if prayers exist for a user and a list of recap documents.

    :param user: The user for whom to check prayer existence.
    :param recap_documents: A list of RECAPDocument instances to check prayers.
    :return: A dictionary where keys are RECAPDocument IDs and values are True
     if a prayer exists for the user and RD.
    """
    existing_prayers = Prayer.objects.filter(
        user=user, recap_document__in=recap_documents
    ).values_list("recap_document_id", flat=True)
    return {rd_id: True async for rd_id in existing_prayers}


async def get_top_prayers() -> QuerySet[RECAPDocument]:
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
            "page_count",
            "is_free_on_pacer",
            "description",
            "docket_entry__entry_number",
            "docket_entry__docket_id",
            "docket_entry__docket__slug",
            "docket_entry__docket__case_name",
            "docket_entry__docket__case_name_short",
            "docket_entry__docket__case_name_full",
            "docket_entry__docket__docket_number",
            "docket_entry__docket__pacer_case_id",
            "docket_entry__docket__court__jurisdiction",
            "docket_entry__docket__court__citation_string",
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

    return documents


async def get_user_prayers(user: User) -> QuerySet[RECAPDocument]:
    user_prayers = Prayer.objects.filter(user=user).values("recap_document_id")

    documents = (
        RECAPDocument.objects.filter(id__in=Subquery(user_prayers))
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
            "page_count",
            "filepath_local",
            "filepath_ia",
            "is_free_on_pacer",
            "description",
            "date_upload",
            "date_created",
            "docket_entry__entry_number",
            "docket_entry__docket_id",
            "docket_entry__docket__slug",
            "docket_entry__docket__case_name",
            "docket_entry__docket__case_name_short",
            "docket_entry__docket__case_name_full",
            "docket_entry__docket__docket_number",
            "docket_entry__docket__pacer_case_id",
            "docket_entry__docket__court__jurisdiction",
            "docket_entry__docket__court__citation_string",
            "docket_entry__docket__court_id",
        )
        .annotate(
            prayer_status=F("prayers__status"),
            prayer_date_created=F("prayers__date_created"),
        )
        .order_by("-prayers__date_created")
    )

    return documents


async def compute_prayer_total_cost(queryset: QuerySet[Prayer]) -> float:
    """
    Computes the total cost of a given queryset of Prayer objects.

    Args:
        queryset: A QuerySet of Prayer objects.

    Returns:
        The total cost of the prayers in the queryset, as a float.
    """
    cost = await (
        queryset.values("recap_document")
        .distinct()
        .annotate(
            price=Case(
                When(recap_document__is_free_on_pacer=True, then=Value(0.0)),
                When(
                    recap_document__page_count__gt=0,
                    then=Least(
                        Value(3.0),
                        F("recap_document__page_count") * Value(0.10),
                    ),
                ),
                default=Value(0.0),
            )
        )
        .aaggregate(Sum("price", default=0.0))
    )

    return cost["price__sum"]


def send_prayer_emails(instance: RECAPDocument) -> None:
    open_prayers = Prayer.objects.filter(
        recap_document=instance, status=Prayer.WAITING
    ).select_related("user")
    # Retrieve email recipients before updating granted prayers.
    email_recipients = [
        {
            "email": prayer["user__email"],
            "date_created": prayer["date_created"],
        }
        for prayer in open_prayers.values("user__email", "date_created")
    ]
    open_prayers.update(status=Prayer.GRANTED)

    # Send email notifications in bulk.
    if email_recipients:
        subject = f"A document you requested is now on CourtListener"
        txt_template = loader.get_template("prayer_email.txt")
        html_template = loader.get_template("prayer_email.html")

        docket = instance.docket_entry.docket
        docket_entry = instance.docket_entry
        document_url = instance.get_absolute_url()
        num_waiting = len(email_recipients)
        doc_price = price(instance)

        messages = []
        for email_recipient in email_recipients:
            context = {
                "docket": docket,
                "docket_entry": docket_entry,
                "rd": instance,
                "document_url": document_url,
                "num_waiting": num_waiting,
                "price": doc_price,
                "date_created": email_recipient["date_created"],
            }
            txt = txt_template.render(context)
            html = html_template.render(context)
            msg = EmailMultiAlternatives(
                subject=subject,
                body=txt,
                from_email=settings.DEFAULT_ALERTS_EMAIL,
                to=[email_recipient["email"]],
                headers={"X-Entity-Ref-ID": f"prayer.rd.pk:{instance.pk}"},
            )
            msg.attach_alternative(html, "text/html")
            messages.append(msg)
        connection = get_connection()
        connection.send_messages(messages)


async def get_user_prayer_history(user: User) -> tuple[int, float]:
    filtered_list = Prayer.objects.filter(
        user=user, status=Prayer.GRANTED
    ).select_related("recap_document")

    count = await filtered_list.acount()

    total_cost = await compute_prayer_total_cost(filtered_list)

    return count, total_cost


@dataclass
class PrayerStats:
    prayer_count: int
    distinct_count: int
    total_cost: str


async def get_lifetime_prayer_stats(
    status: int,
) -> (
    PrayerStats
):  # status can be only 1 (WAITING) or 2 (GRANTED) based on the Prayer model

    cache_key = f"prayer-stats-{status}"

    data = await cache.aget(cache_key)
    if data is not None:
        return PrayerStats(**data)

    prayer_by_status = Prayer.objects.filter(status=status)

    prayer_count = await prayer_by_status.acount()

    distinct_prayers = (
        await prayer_by_status.values("recap_document").distinct().acount()
    )

    total_cost = await compute_prayer_total_cost(
        prayer_by_status.select_related("recap_document")
    )

    data = {
        "prayer_count": prayer_count,
        "distinct_count": distinct_prayers,
        "total_cost": f"{total_cost:,.2f}",
    }
    one_day = 60 * 60 * 24
    await cache.aset(cache_key, data, one_day)

    return PrayerStats(**data)
