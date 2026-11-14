"""Build a copy of the data a user has stored in CourtListener.

This backs the "Export my data" page, which lets people exercise their right
to access their data (GDPR, CCPA, etc.). Most accounts hold a few dozen rows,
so the export is built in memory while the user waits.
"""

from typing import Any

from django.contrib.auth.models import User
from django.db.models import F, Field, Model, Prefetch, QuerySet
from django.utils.timezone import localdate, now

from cl.alerts.models import Alert, DocketAlert
from cl.api.utils import get_user_api_usage
from cl.donate.models import Donation, MonthlyDonation, NeonMembership
from cl.favorites.models import Note, Prayer, UserTag
from cl.search.models import Docket, OpinionCluster, SearchQuery
from cl.sso.models import AuthEvent
from cl.users.models import UserProfile
from cl.visualizations.models import SCOTUSMap

# Fields are allowlisted, not blocklisted, so a column added to one of these
# models later stays out of exports until somebody decides it belongs there.
# Credentials (password hashes, alert secret keys, activation keys) and staff
# fields (notes, testing flags) are deliberately absent.
USER_FIELDS = (
    "username",
    "first_name",
    "last_name",
    "email",
    "date_joined",
    "last_login",
)
PROFILE_FIELDS = (
    "employer",
    "address1",
    "address2",
    "city",
    "state",
    "zip_code",
    "email_confirmed",
    "recap_email",
    "plaintext_preferred",
    "auto_subscribe",
    "docket_default_order_desc",
    "prayers_public",
    "save_query_history",
)


def _rows(
    queryset: QuerySet[Any], *fields: str, **expressions: Any
) -> list[dict[str, Any]]:
    """Return a queryset's rows as dicts, ready for JSON.

    Choice fields are converted from their stored codes (e.g. "dly") to their
    human-readable labels (e.g. "Daily"), so the export makes sense to someone
    who can't read our source code.

    Args:
        queryset: The rows to export.
        *fields: Names of concrete fields on the queryset's model. Only these
            have their choice codes converted.
        **expressions: Extra values to include, such as F() lookups that pull
            a case name across a relation.

    Returns:
        One dict per row, keyed by field or expression name.
    """
    model: type[Model] = queryset.model
    labels = {
        name: dict(field.flatchoices)
        for name in fields
        if isinstance(field := model._meta.get_field(name), Field)
        and field.choices
    }
    rows = list(queryset.values(*fields, **expressions))
    for row in rows:
        for name, choices in labels.items():
            row[name] = choices.get(row[name], row[name])
    return rows


def _account(user: User) -> dict[str, Any]:
    """Return the user's account details and settings."""
    profile = UserProfile.objects.get(user=user)
    account = {name: getattr(user, name) for name in USER_FIELDS}
    account |= {name: getattr(profile, name) for name in PROFILE_FIELDS}
    # A bar membership's string form is its state's full name.
    account["bar_memberships"] = [
        str(bar) for bar in profile.barmembership.all()
    ]
    return account


def _tags(user: User) -> list[dict[str, Any]]:
    """Return the user's docket tags, each with the dockets it holds."""
    dockets = Prefetch(
        "dockets", queryset=Docket.objects.only("pk", "case_name")
    )
    tags = (
        UserTag.objects.filter(user=user)
        .order_by("pk")
        .prefetch_related(dockets)
    )
    return [
        {
            "date_created": tag.date_created,
            "date_modified": tag.date_modified,
            "name": tag.name,
            "title": tag.title,
            "description": tag.description,
            "published": tag.published,
            "view_count": tag.view_count,
            "dockets": [
                {"docket_id": docket.pk, "case_name": docket.case_name}
                for docket in tag.dockets.all()
            ],
        }
        for tag in tags
    ]


def _visualizations(user: User) -> list[dict[str, Any]]:
    """Return the user's citation network visualizations.

    Deleted visualizations are included, since we still hold them.
    """
    clusters = Prefetch(
        "clusters", queryset=OpinionCluster.objects.only("pk", "case_name")
    )
    maps = (
        SCOTUSMap.objects.filter(user=user)
        .order_by("pk")
        .select_related("cluster_start", "cluster_end")
        .prefetch_related(clusters)
    )
    return [
        {
            "date_created": viz.date_created,
            "date_modified": viz.date_modified,
            "title": viz.title,
            "notes": viz.notes,
            "cluster_start_id": viz.cluster_start_id,
            "cluster_start_name": viz.cluster_start.case_name,
            "cluster_end_id": viz.cluster_end_id,
            "cluster_end_name": viz.cluster_end.case_name,
            "published": viz.published,
            "date_published": viz.date_published,
            "deleted": viz.deleted,
            "date_deleted": viz.date_deleted,
            "view_count": viz.view_count,
            "clusters": [
                {"cluster_id": cluster.pk, "case_name": cluster.case_name}
                for cluster in viz.clusters.all()
            ],
        }
        for viz in maps
    ]


def build_user_data_export(user: User) -> dict[str, Any]:
    """Gather everything we can give a user about their account.

    The result holds dates, decimals and IP addresses, so serialize it with
    `DjangoJSONEncoder`. Related records are identified by their ID (e.g. a
    docket ID), with a case name alongside where one helps.

    Data kept outside our database (Neon, Stripe, Zoho Desk) is not included,
    nor are logs we keep for operating the site, like sent emails, webhook
    deliveries and RECAP uploads.

    Args:
        user: The user whose data to export.

    Returns:
        A dict with one key per kind of data.
    """
    return {
        "export_info": {
            "date_generated": now(),
            "description": (
                "A copy of the data CourtListener holds about your account. "
                "Items such as dockets, opinion clusters and RECAP documents "
                "are identified by their CourtListener IDs, which work with "
                "the CourtListener API."
            ),
        },
        "account": _account(user),
        "search_alerts": _rows(
            Alert.objects.filter(user=user).order_by("pk"),
            "date_created",
            "date_modified",
            "name",
            "query",
            "rate",
            "alert_type",
            "date_last_hit",
        ),
        "docket_alerts": _rows(
            DocketAlert.objects.filter(user=user).order_by("pk"),
            "date_created",
            "date_modified",
            "docket_id",
            "alert_type",
            "date_last_hit",
            case_name=F("docket__case_name"),
        ),
        "notes": _rows(
            Note.objects.filter(user=user).order_by("pk"),
            "date_created",
            "date_modified",
            "object_id",
            "name",
            "notes",
            item_type=F("content_type__model"),
        ),
        "tags": _tags(user),
        "prayers": _rows(
            Prayer.objects.filter(user=user).order_by("pk"),
            "date_created",
            "recap_document_id",
            "status",
            docket_id=F("recap_document__docket_entry__docket_id"),
            case_name=F("recap_document__docket_entry__docket__case_name"),
            document_number=F("recap_document__document_number"),
            attachment_number=F("recap_document__attachment_number"),
        ),
        "visualizations": _visualizations(user),
        "donations": _rows(
            Donation.objects.filter(donor=user).order_by("pk"),
            "date_created",
            "amount",
            "payment_provider",
            "status",
            "clearing_date",
            "send_annual_reminder",
        ),
        "monthly_donations": _rows(
            MonthlyDonation.objects.filter(donor=user).order_by("pk"),
            "date_created",
            "enabled",
            "payment_provider",
            "monthly_donation_amount",
            "monthly_donation_day",
        ),
        "memberships": _rows(
            NeonMembership.objects.filter(user=user),
            "date_created",
            "level",
            "payment_status",
            "termination_date",
        ),
        "search_history": _rows(
            SearchQuery.objects.filter(user=user).order_by("pk"),
            "date_created",
            "get_params",
            "source",
            "engine",
            "query_mode",
        ),
        "login_history": _rows(
            AuthEvent.objects.filter(user=user).order_by("pk"),
            "date_created",
            "method",
            "outcome",
            "ip_address",
        ),
        # Usage is logged per server-local day, so ask for the same days.
        "api_usage_by_day": get_user_api_usage(
            user.pk, str(localdate(user.date_joined)), str(localdate())
        ),
    }
