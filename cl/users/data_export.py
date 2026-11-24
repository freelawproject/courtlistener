"""Build a copy of the data a user has stored in CourtListener.

This backs the "Export my data" page, which lets people exercise their right
to access their data (GDPR, CCPA, etc.). Most accounts hold a few dozen rows,
so the export is built in memory while the user waits.
"""

from typing import Any

from django.contrib.auth.models import User
from django.core import serializers
from django.db.models import Model, QuerySet
from django.utils.timezone import now
from django.views.decorators.debug import sensitive_variables
from redis import ConnectionError

from cl.alerts.models import Alert, DocketAlert
from cl.donate.models import Donation, MonthlyDonation, NeonMembership
from cl.favorites.models import DocketTag, Note, Prayer, UserTag
from cl.lib.ratelimiter import get_ratelimit_cache
from cl.search.models import SearchQuery
from cl.users.models import BarMembership, UserProfile
from cl.visualizations.models import SCOTUSMap

# Credentials, access flags and fields managed by staff. Every other field on
# the exported models goes out as stored, so new columns are exported
# automatically; add them here if they shouldn't be.
EXCLUDED_FIELDS: dict[type[Model], set[str]] = {
    User: {
        "groups",
        "is_active",
        "is_staff",
        "is_superuser",
        "password",
        "user_permissions",
    },
    UserProfile: {
        "activation_key",
        "avatar",
        "is_tester",
        "key_expires",
        "notes",
        "stub_account",
    },
    Alert: {"secret_key"},
    DocketAlert: {"secret_key"},
}


EXPORT_INTERVAL = 60 * 60 * 24  # Seconds a user waits between exports


def _serialize(queryset: QuerySet[Any]) -> list[dict[str, Any]]:
    """Dump a queryset with Django's serializer, minus excluded fields.

    Fields linking back to a user are dropped too.

    Related objects appear as IDs. Django skips many-to-many fields that
    have a custom through model (e.g. UserTag.dockets), so export the
    through model's rows instead.

    Args:
        queryset: The rows to export.

    Returns:
        One {"model", "pk", "fields"} dict per row, ordered by primary key.
    """
    model = queryset.model
    opts = model._meta
    excluded = EXCLUDED_FIELDS.get(model, set())
    fields = [
        field.name
        for field in (*opts.concrete_fields, *opts.many_to_many)
        # Every exported row belongs to the user, so links back to them (e.g.
        # Alert.user, Donation.donor) add nothing.
        if field.name not in excluded and field.related_model is not User
    ]
    return serializers.serialize(
        "python", queryset.order_by("pk"), fields=fields
    )


@sensitive_variables()
def build_user_data_export(user: User) -> dict[str, Any]:
    """Gather everything we can give a user about their account.

    The result holds dates and decimals, so encode it with
    `DjangoJSONEncoder`, which `JsonResponse` uses by default. Data kept
    outside our database (Neon, Stripe, Zoho Desk) is not included, nor are
    logs we keep for operating the site, like sign-ins, sent emails, webhook
    deliveries and RECAP uploads.

    Args:
        user: The user whose data to export.

    Returns:
        A dict with one key per kind of data.
    """
    # One-to-one with the user, so exported as a single object (or null).
    single: dict[str, QuerySet[Any]] = {
        "user": User.objects.filter(pk=user.pk),
        "profile": UserProfile.objects.filter(user=user),
        "membership": NeonMembership.objects.filter(user=user),
    }
    many: dict[str, QuerySet[Any]] = {
        "bar_memberships": BarMembership.objects.filter(
            userprofile__user=user
        ),
        "search_alerts": Alert.objects.filter(user=user),
        "docket_alerts": DocketAlert.objects.filter(user=user),
        "notes": Note.objects.filter(user=user),
        "tags": UserTag.objects.filter(user=user),
        "tagged_dockets": DocketTag.objects.filter(tag__user=user),
        "prayers": Prayer.objects.filter(user=user),
        "visualizations": SCOTUSMap.objects.filter(user=user),
        "donations": Donation.objects.filter(donor=user),
        "monthly_donations": MonthlyDonation.objects.filter(donor=user),
        "search_history": SearchQuery.objects.filter(user=user),
    }
    export: dict[str, Any] = {"date_generated": now()}
    export |= {
        name: next(iter(_serialize(qs)), None) for name, qs in single.items()
    }
    export |= {name: _serialize(qs) for name, qs in many.items()}
    profile = UserProfile.objects.get(user=user)
    export["total_api_requests"] = profile.total_api_usage
    return export


def claim_daily_export(user: User) -> bool:
    """Record an export for the user, unless they already had one today.

    Call this only once the export is ready to send, so that a wrong
    password or an error while building the export doesn't use up the day.

    Args:
        user: The user who wants an export.

    Returns:
        True if the export may go ahead, False if the user already had one in
        the last 24 hours. Also True if the cache is unreachable, so an outage
        doesn't block exports.
    """
    try:
        # add() only writes when the key is absent, so of two simultaneous
        # requests, only one gets True.
        return get_ratelimit_cache().add(
            f"rl:data-export:{user.pk}", True, EXPORT_INTERVAL
        )
    except ConnectionError:
        return True
