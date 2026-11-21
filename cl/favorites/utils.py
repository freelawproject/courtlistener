"""Helpers for notes, prayers, and prayer statistics and emails."""

import time
from dataclasses import asdict, dataclass

from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth.models import AnonymousUser, User
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db import models
from django.db.models import (
    Case,
    CharField,
    Count,
    F,
    OuterRef,
    Prefetch,
    Q,
    QuerySet,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Concat, Least
from django.template import loader

from cl.api.models import Webhook, WebhookEventType
from cl.api.tasks import send_pray_and_pay_webhooks
from cl.audio.models import Audio
from cl.custom_filters.templatetags.pacer import price
from cl.favorites.models import GenericCount, Note, Prayer, PrayerAvailability
from cl.favorites.selectors import prayer_eligible
from cl.search.models import (
    Docket,
    OpinionCluster,
    RECAPDocument,
    SCOTUSDocument,
)

# Models that can have a Note attached, mapped to the bucket label the
# profile Notes page groups them under (cl.users.views.view_notes()).
NOTEABLE_MODELS: dict[type[models.Model], str] = {
    Docket: "Dockets",
    OpinionCluster: "Opinions",
    Audio: "Oral Arguments",
    RECAPDocument: "Documents",
    SCOTUSDocument: "Documents",
}


def get_notes_for(obj: models.Model) -> QuerySet[Note]:
    """Return the Notes attached to a given object, across all users.

    Args:
        obj: A noteable model instance (see NOTEABLE_MODELS).

    Returns:
        A queryset of matching Note rows.
    """
    content_type = ContentType.objects.get_for_model(type(obj))
    return Note.objects.filter(content_type=content_type, object_id=obj.pk)


def repoint_notes(
    main_object: models.Model, version_object: models.Model
) -> None:
    """Repoint Notes from version_object onto main_object.

    For use when merging two noteable rows into one (e.g.
    merge_opinion_versions).

    A user who already has a Note on main_object keeps that one; the
    version's Note is left pointed at version_object, to be cleaned up by
    delete_orphaned_notes when it's deleted.

    Args:
        main_object: The noteable object absorbing version_object's
            Notes.
        version_object: The noteable object about to be deleted.
    """
    existing_user_ids = get_notes_for(main_object).values_list(
        "user_id", flat=True
    )
    get_notes_for(version_object).exclude(
        user_id__in=existing_user_ids
    ).update(
        content_type=ContentType.objects.get_for_model(type(main_object)),
        object_id=main_object.pk,
    )


def get_note_for_target(
    model_class: type[models.Model],
    object_id: int | str,
    user: AnonymousUser | User,
) -> Note | None:
    """Return the given user's Note for a noted object, identified by its model class and pk, if any.

    Args:
        model_class: The model class object_id belongs to.
        object_id: The pk of the noted object.
        user: The user requesting their Note, possibly anonymous.

    Returns:
        The user's Note for the object, or None if anonymous or not
        found.
    """
    if not user.is_authenticated:
        return None

    content_type = ContentType.objects.get_for_model(model_class)
    return Note.objects.filter(
        content_type=content_type, object_id=object_id, user=user
    ).first()


async def create_prayer(
    user: User,
    recap_document: RECAPDocument,
    is_eligible: bool | None = None,
) -> Prayer | None:
    """Create a waiting prayer for the user on an unavailable document.

    Returns None when the user reached their daily limit, the document is
    already available, or the user already prayed for it.

    :param is_eligible: The result of prayer_eligible() when the caller
        already has it, to avoid querying it twice. Checked here if omitted.
    """
    if is_eligible is None:
        is_eligible, _ = await prayer_eligible(user)

    if not is_eligible or recap_document.is_available:
        return None

    new_prayer, created = await Prayer.objects.aget_or_create(
        user=user, recap_document=recap_document
    )
    if not created:
        return None

    return new_prayer


async def delete_prayer(user: User, recap_document: RECAPDocument) -> bool:
    """Delete a user's waiting prayer for a document.

    Returns:
        Whether a prayer was deleted.
    """
    deleted, _ = await Prayer.objects.filter(
        user=user, recap_document=recap_document, status=Prayer.WAITING
    ).adelete()

    return deleted > 0


async def get_prayer_counts_in_bulk(
    recap_documents: list[RECAPDocument],
) -> dict[int, int]:
    """Retrieve the count of prayers with a status of "WAITING" for a list of recap documents.

    Args:
        recap_documents: A list of RECAPDocument instances to filter prayers.

    Returns:
        A dictionary where keys are RECAPDocument IDs and values are the
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

    Args:
        user: The user for whom to check prayer existence.
        recap_documents: A list of RECAPDocument instances to check prayers.

    Returns:
        A dictionary where keys are RECAPDocument IDs and values are True
        if a prayer exists for the user and RD.
    """
    existing_prayers = Prayer.objects.filter(
        user=user, recap_document__in=recap_documents
    ).values_list("recap_document_id", flat=True)
    return {rd_id: True async for rd_id in existing_prayers}


async def get_top_prayers() -> QuerySet[RECAPDocument]:
    """Retrieve the most desired documents that have open prayers.

    It first ranks by the number of requests and then by the number of views
    the particular docket has received.

    Returns:
        A queryset of RECAPDocuments in descending order of preference.
    """
    waiting_prayers = Prayer.objects.filter(status=Prayer.WAITING).values(
        "recap_document_id"
    )

    # Subquery to fetch the view_count from GenericCount
    view_count_subquery = Subquery(
        GenericCount.objects.filter(
            label=Concat(
                Value("d."),
                OuterRef("docket_entry__docket_id"),
                Value(":view"),
                output_field=CharField(),
            )
        ).values("value")[:1]
    )

    # Annotate each RECAPDocument with the number of prayers and the number of docket views, plus whether it is currently unavailable
    return (
        RECAPDocument.objects.filter(id__in=Subquery(waiting_prayers))
        .select_related(
            "docket_entry",
            "docket_entry__docket",
            "docket_entry__docket__court",
        )
        .prefetch_related("prayeravailability")
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
            "prayeravailability__id",
            "prayeravailability__last_checked",
        )
        .annotate(
            prayer_count=Count(
                "prayers", filter=Q(prayers__status=Prayer.WAITING)
            ),
            view_count=view_count_subquery,
            doc_unavailable=Case(
                When(prayeravailability__id__isnull=False, then=Value(True)),
                default=Value(False),
            ),
            last_checked=F("prayeravailability__last_checked__date"),
        )
        .order_by(
            "doc_unavailable", "last_checked", "-prayer_count", "-view_count"
        )
    )


async def get_user_prayers(
    user: User, status: str | None = None
) -> QuerySet[RECAPDocument]:
    """Get the documents a user prayed for, most recent prayer first.

    Optionally only includes prayers with the given status. Each document
    is annotated with its prayer's status and creation date.
    """
    filters = Q(prayers__user=user)
    if status is not None:
        filters &= Q(prayers__status=status)

    return (
        RECAPDocument.objects.filter(filters)
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


async def compute_prayer_total_cost(queryset: QuerySet[Prayer]) -> float:
    """Computes the total cost of a given queryset of Prayer objects.

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
                default=Value(0.91),
            )
        )
        .aaggregate(Sum("price", default=0.0))
    )

    return round(cost["price__sum"], 1)


def send_prayer_emails(instance: RECAPDocument) -> None:
    """Grant a document's waiting prayers and notify the users of all its granted prayers.

    Queues each user's enabled pray-and-pay webhooks, clears the document's
    availability record, and emails the users. Does nothing if no prayers
    were waiting.
    """
    # Update prayers to GRANTED status and check if any were updated
    updated_count = Prayer.objects.filter(
        recap_document=instance, status=Prayer.WAITING
    ).update(status=Prayer.GRANTED)

    # Early return if no prayers were granted
    if not updated_count:
        return

    # Fetch granted prayers with related user and their webhooks
    granted_prayers = (
        Prayer.objects.filter(recap_document=instance, status=Prayer.GRANTED)
        .select_related("user")
        .prefetch_related(
            Prefetch(
                "user__webhooks",
                queryset=Webhook.objects.filter(
                    event_type=WebhookEventType.PRAY_AND_PAY, enabled=True
                ),
                to_attr="granted_prayer_webhooks",
            )
        )
    )

    for prayer in granted_prayers:
        # Send webhook for each enabled webhook
        for webhook in prayer.user.granted_prayer_webhooks:
            send_pray_and_pay_webhooks.delay(prayer.pk, webhook.pk)

    # copying code from cl/favorites/tasks.py to account for circumstance where
    # someone buys a document from PACER despite it being marked sealed on RECAP
    PrayerAvailability.objects.filter(recap_document=instance).delete()

    # Send email notifications in bulk.
    subject = "A document you requested is now on CourtListener"
    txt_template = loader.get_template("prayer_email.txt")
    html_template = loader.get_template("prayer_email.html")

    docket = instance.docket_entry.docket
    docket_entry = instance.docket_entry
    document_url = instance.get_absolute_url()
    num_waiting = granted_prayers.count()
    doc_price = price(instance)

    messages = []
    for prayer in granted_prayers:
        context = {
            "docket": docket,
            "docket_entry": docket_entry,
            "rd": instance,
            "document_url": document_url,
            "num_waiting": num_waiting,
            "price": doc_price,
            "date_created": prayer.date_created,
        }
        txt = txt_template.render(context)
        html = html_template.render(context)
        msg = EmailMultiAlternatives(
            subject=subject,
            body=txt,
            from_email=settings.DEFAULT_ALERTS_EMAIL,
            to=[prayer.user.email],
            headers={"X-Entity-Ref-ID": f"prayer.rd.pk:{instance.pk}"},
        )
        msg.attach_alternative(html, "text/html")
        messages.append(msg)
    connection = get_connection()
    connection.send_messages(messages)


@dataclass
class PrayerStats:
    """Counts and total cost of a set of prayers."""

    prayer_count: int
    total_cost: str
    distinct_count: int | None = None
    distinct_users: int | None = None


async def get_user_prayer_history(user: User) -> PrayerStats:
    """Get the count and total cost of a user's granted prayers, cached for a minute."""
    cache_key = f"prayer-stats-{user}"

    data = await cache.aget(cache_key)
    if data is not None:
        return PrayerStats(**data)

    filtered_list = Prayer.objects.filter(
        user=user, status=Prayer.GRANTED
    ).select_related("recap_document")

    count = await filtered_list.acount()

    total_cost = await compute_prayer_total_cost(filtered_list)

    data = {
        "prayer_count": count,
        "total_cost": f"{total_cost:,.2f}",
    }

    one_minute = 60
    await cache.aset(cache_key, data, one_minute)

    return PrayerStats(**data)


LIFETIME_PRAYER_STATS_REFRESH_SECONDS = 60 * 10


def lifetime_prayer_stats_cache_key(status: int) -> str:
    """Return the cache key holding the lifetime stats for a prayer status."""
    return f"lifetime-prayer-stats-{status}"


def lifetime_prayer_stats_lock_key(status: int) -> str:
    """Return the cache key marking a pending refresh of a status's stats."""
    return f"lifetime-prayer-stats-refreshing-{status}"


async def compute_lifetime_prayer_stats(status: int) -> PrayerStats:
    """Compute the stats for all prayers with a status and cache them.

    This is slow on production data: the total cost joins every matching
    prayer to its RECAP document. Callers other than background tasks SHOULD
    use get_lifetime_prayer_stats() instead.

    Args:
        status: Prayer.WAITING or Prayer.GRANTED.

    Returns:
        The freshly computed stats.
    """
    prayer_by_status = Prayer.objects.filter(status=status)
    counts = await prayer_by_status.aaggregate(
        prayer_count=Count("id"),
        distinct_count=Count("recap_document", distinct=True),
        distinct_users=Count("user", distinct=True),
    )
    total_cost = await compute_prayer_total_cost(
        prayer_by_status.select_related("recap_document")
    )
    stats = PrayerStats(
        prayer_count=counts["prayer_count"],
        distinct_count=counts["distinct_count"],
        distinct_users=counts["distinct_users"],
        total_cost=f"{total_cost:,.2f}",
    )
    # Never expire the entry, so readers can keep serving it while a refresh
    # runs. Freshness is tracked by refresh_after instead.
    await cache.aset(
        lifetime_prayer_stats_cache_key(status),
        {
            "refresh_after": time.time()
            + LIFETIME_PRAYER_STATS_REFRESH_SECONDS,
            "stats": asdict(stats),
        },
        timeout=None,
    )
    return stats


async def get_lifetime_prayer_stats(status: int) -> PrayerStats:
    """Get stats for all prayers with a status.

    Includes the number of prayers, distinct documents, distinct users, and
    the total cost.

    The stats are served from the cache and can be up to about ten minutes
    stale: once they're older than that, the next call queues a background
    refresh and returns the cached stats meanwhile. Only when nothing is
    cached at all (e.g. after Redis is flushed) are they computed inline,
    which is slow.

    Args:
        status: Prayer.WAITING or Prayer.GRANTED.

    Returns:
        The stats for prayers with that status.
    """
    entry = await cache.aget(lifetime_prayer_stats_cache_key(status))
    if entry is None:
        return await compute_lifetime_prayer_stats(status)

    # cache.aadd() only succeeds for the first caller, so stale reads queue
    # one refresh at a time. The lock expires on its own if the task dies.
    if time.time() > entry["refresh_after"] and await cache.aadd(
        lifetime_prayer_stats_lock_key(status),
        True,
        LIFETIME_PRAYER_STATS_REFRESH_SECONDS,
    ):
        # Imported here because cl.favorites.tasks imports this module.
        from cl.favorites.tasks import refresh_lifetime_prayer_stats

        await sync_to_async(refresh_lifetime_prayer_stats.delay)(status)
    return PrayerStats(**entry["stats"])


def prayer_unavailable(instance: RECAPDocument, user_pk: int | None) -> None:
    """Email a user that the document they prayed for can't be bought.

    Does nothing if the user has no waiting prayer for the document.
    """
    open_prayers = Prayer.objects.filter(
        recap_document=instance, status=Prayer.WAITING
    ).select_related("user")

    user_prayer = open_prayers.filter(user__pk=user_pk).first()

    if not user_prayer:
        return

    email_recipients = [
        {
            "email": user_prayer.user.email,
            "date_created": user_prayer.date_created,
        }
    ]

    # Send email notification.
    subject = "A document you requested is unavailable for purchase"
    txt_template = loader.get_template("prayer_email_unavailable.txt")
    html_template = loader.get_template("prayer_email_unavailable.html")

    docket = instance.docket_entry.docket
    docket_entry = instance.docket_entry
    document_url = instance.get_absolute_url()
    num_waiting = open_prayers.count()
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
