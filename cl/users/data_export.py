"""Build a copy of the data a user has stored in CourtListener.

This backs the "Export my data" page, which lets people exercise their right
to access their data (GDPR, CCPA, etc.). Most accounts hold a few dozen rows,
so the export is built in memory while the user waits.
"""

from typing import Any

from django.contrib.auth.models import User
from django.core import serializers
from django.db.models import Model, QuerySet
from django.utils.timezone import localdate, now

from cl.alerts.models import Alert, DocketAlert
from cl.api.utils import get_user_api_usage
from cl.donate.models import Donation, MonthlyDonation, NeonMembership
from cl.favorites.models import DocketTag, Note, Prayer, UserTag
from cl.search.models import SearchQuery
from cl.sso.models import AuthEvent
from cl.users.models import BarMembership, UserProfile
from cl.visualizations.models import SCOTUSMap

# Credentials and fields written by staff. Every other field on the exported
# models goes out as stored, so new columns are exported automatically; add
# them here if they shouldn't be.
EXCLUDED_FIELDS: dict[type[Model], set[str]] = {
    User: {"password"},
    UserProfile: {
        "activation_key",
        "avatar",
        "is_tester",
        "key_expires",
        "notes",
    },
    Alert: {"secret_key"},
    DocketAlert: {"secret_key"},
}


def _serialize(queryset: QuerySet[Any]) -> list[dict[str, Any]]:
    """Dump a queryset with Django's serializer, minus excluded fields.

    Related objects appear as IDs. Django skips many-to-many fields that
    have a custom through model (e.g. UserTag.dockets), so export the
    through model's rows instead.

    Args:
        queryset: The rows to export.

    Returns:
        One {"model", "pk", "fields"} dict per row, ordered by primary key.
    """
    model = queryset.model
    fields = None
    if excluded := EXCLUDED_FIELDS.get(model):
        opts = model._meta
        fields = [
            field.name
            for field in (*opts.concrete_fields, *opts.many_to_many)
            if field.name not in excluded
        ]
    return serializers.serialize(
        "python", queryset.order_by("pk"), fields=fields
    )


def build_user_data_export(user: User) -> dict[str, Any]:
    """Gather everything we can give a user about their account.

    The result holds dates and decimals, so serialize it with
    `DjangoJSONEncoder`. Data kept outside our database (Neon, Stripe, Zoho
    Desk) is not included, nor are logs we keep for operating the site, like
    sent emails, webhook deliveries and RECAP uploads.

    Args:
        user: The user whose data to export.

    Returns:
        A dict with one key per kind of data.
    """
    querysets: dict[str, QuerySet[Any]] = {
        "user": User.objects.filter(pk=user.pk),
        "profile": UserProfile.objects.filter(user=user),
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
        "memberships": NeonMembership.objects.filter(user=user),
        "search_history": SearchQuery.objects.filter(user=user),
        "login_history": AuthEvent.objects.filter(user=user),
    }
    export: dict[str, Any] = {"date_generated": now()}
    export |= {name: _serialize(qs) for name, qs in querysets.items()}
    # Usage is logged per server-local day, so ask for the same days.
    export["api_usage_by_day"] = get_user_api_usage(
        user.pk, str(localdate(user.date_joined)), str(localdate())
    )
    return export
