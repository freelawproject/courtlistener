from typing import cast

from django.apps import apps
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth.forms import UserChangeForm
from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models import Model, QuerySet
from django.forms import BaseInlineFormSet
from django.http import HttpRequest
from rest_framework.authtoken.models import Token

from cl.alerts.admin import AlertInline, DocketAlertInline
from cl.api.admin import APIThrottleInline, WebhookInline
from cl.api.utils import (
    apply_membership_throttles,
    clear_membership_throttles,
)
from cl.donate.admin import (
    DonationInline,
    MonthlyDonationInline,
    NeonMembershipInline,
)
from cl.donate.models import NeonMembership
from cl.favorites.admin import NoteInline, PrayerInline, UserTagInline
from cl.favorites.models import UserTag
from cl.lib.admin import (
    AdminLink,
    AdminLinkConfig,
    AdminTweaksMixin,
    generate_admin_links,
)
from cl.lib.auth import filter_by_email
from cl.search.models import SearchQuery
from cl.users.models import (
    BarMembership,
    EmailFlag,
    EmailSent,
    FailedEmail,
    UserProfile,
)

UserProxyEvent: type[Model] = cast(
    type[Model], apps.get_model("users", "UserProxyEvent")
)
UserProfileEvent: type[Model] = cast(
    type[Model], apps.get_model("users", "UserProfileEvent")
)


def _is_complete_email(value: str) -> bool:
    """Return True if value is a syntactically complete email address."""
    try:
        validate_email(value)
    except ValidationError:
        return False
    return True


class TokenInline(admin.StackedInline):
    model = Token


class UserProfileInline(admin.StackedInline):
    model = UserProfile


class CustomUserChangeForm(UserChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Ensure user_permissions field uses an optimized queryset
        if "user_permissions" in self.fields:
            self.fields[
                "user_permissions"
            ].queryset = Permission.objects.select_related("content_type")


# Replace the normal User admin with our better one.
admin.site.unregister(User)


@admin.register(User)
class UserAdmin(admin.ModelAdmin, AdminTweaksMixin):
    form = CustomUserChangeForm  # optimize queryset for user_permissions field
    change_form_template = "admin/change_form_with_custom_links.html"
    readonly_fields = ("api_calls_count",)
    inlines = (
        UserProfileInline,
        DonationInline,
        MonthlyDonationInline,
        PrayerInline,
        AlertInline,
        DocketAlertInline,
        NoteInline,
        UserTagInline,
        NeonMembershipInline,
        TokenInline,
        WebhookInline,
        APIThrottleInline,
    )
    list_display = (
        "username",
        "get_email_confirmed",
        "get_stub_account",
    )
    list_filter = (
        "is_superuser",
        "profile__email_confirmed",
        "profile__stub_account",
    )
    search_help_text = (
        "Search Users by username, first name, last name, email, or pk."
    )
    search_fields = (
        "username",
        "first_name",
        "last_name",
        "email",
        "pk",
    )
    actions = ["refresh_api_throttles"]

    def get_search_results(
        self,
        request: HttpRequest,
        queryset: QuerySet[User],
        search_term: str,
    ) -> tuple[QuerySet[User], bool]:
        """Filter the changelist, using the LOWER(email) index for complete addresses.

        Domain or partial terms keep the default icontains search.

        :param request: The current HTTP request.
        :param queryset: The changelist queryset to filter.
        :param search_term: The raw string typed into the search box.
        :return: Two-tuple of the filtered queryset and whether the caller
            needs to de-duplicate the results.
        """
        term = search_term.strip()
        if _is_complete_email(term):
            return filter_by_email(queryset, term), False
        return super().get_search_results(request, queryset, search_term)

    def save_related(
        self,
        request: HttpRequest,
        form: UserChangeForm,
        formsets: list[BaseInlineFormSet],
        change: bool,
    ) -> None:
        """Save the user's inlines, then resync API throttles if the
        membership inline was changed.

        Runs after the inline formsets are saved so that the membership we
        read reflects what the admin just submitted. MANUAL-source throttles
        are never touched.

        :param request: The current HTTP request.
        :param form: The user form.
        :param formsets: The inline formsets submitted with the form.
        :param change: Whether an existing user is being changed.
        """
        super().save_related(request, form, formsets, change)

        if not any(
            fs.model is NeonMembership and fs.has_changed() for fs in formsets
        ):
            return

        user = form.instance
        try:
            membership = NeonMembership.objects.get(user=user)
        except NeonMembership.DoesNotExist:
            membership = None

        if not membership or not membership.is_active:
            # Membership removed or lapsed: drop the throttles it granted,
            # mirroring what the Neon deletion webhook does.
            clear_membership_throttles(user)
            return

        if not apply_membership_throttles(
            user, membership.level, clear_cache=True
        ):
            self.message_user(
                request,
                f"Could not refresh throttles (no matching membership level): {user.username}",
                level=messages.WARNING,
            )
            return
        self.message_user(
            request,
            f"Refreshed API throttles for {user.username}.",
            level=messages.SUCCESS,
        )

    @admin.action(
        description="Refresh API throttles from active Neon membership"
    )
    def refresh_api_throttles(self, request, queryset):
        """Resync MEMBERSHIP-source API throttles for the selected users
        from each user's current active Neon membership.

        MANUAL-source throttles are never touched (the helper only
        manages MEMBERSHIP rows).
        """
        refreshed = 0
        skipped: list[str] = []
        not_updated: list[str] = []

        for user in queryset.select_related("membership"):
            try:
                membership = user.membership
            except NeonMembership.DoesNotExist:
                membership = None

            if not membership or not membership.is_active:
                skipped.append(user.username)
                continue

            if apply_membership_throttles(user, membership.level):
                refreshed += 1
            else:
                not_updated.append(user.username)

        if refreshed:
            self.message_user(
                request,
                f"Refreshed API throttles for {refreshed} user(s).",
                level=messages.SUCCESS,
            )
        if skipped:
            self.message_user(
                request,
                f"Skipped (no active Neon membership): {', '.join(skipped)}",
                level=messages.ERROR,
            )
        if not_updated:
            self.message_user(
                request,
                f"Could not refresh throttles (no matching membership level): {', '.join(not_updated)}",
                level=messages.ERROR,
            )

    def api_calls_count(self, obj):
        if obj.id is None:
            # New user, no API usage, bail.
            return 0

        return obj.profile.total_api_usage

    api_calls_count.short_description = "API Calls Count"

    def change_view(self, request, object_id, form_url="", extra_context=None):
        """Add links to related event admin pages filtered by user/profile."""
        extra_context = extra_context or {}
        user = self.get_object(request, object_id)

        custom_links: list[AdminLinkConfig] = [
            {
                "label": "UserProxy Events",
                "model_class": UserProxyEvent,
                "query_params": {"pgh_obj": object_id},
            },
            {
                "label": "UserProfile Events",
                "model_class": UserProfileEvent,
                "query_params": {"pgh_obj": user.profile.pk},
            },
            {
                "label": "Search Queries",
                "model_class": SearchQuery,
                "query_params": {"user": object_id},
            },
            {
                "label": "Tags",
                "model_class": UserTag,
                "query_params": {"user": object_id},
            },
        ]

        links = generate_admin_links(custom_links)
        if user is not None:
            links.extend(self._get_neon_links(user.pk))
        extra_context["custom_links"] = links

        return super().change_view(
            request, object_id, form_url, extra_context=extra_context
        )

    @staticmethod
    def _get_neon_links(user_id: int) -> list[AdminLink]:
        """Build links to a user's Neon account and membership records.

        Links are only returned for records we have a Neon ID for, so users
        without a Neon account or membership get no link.

        :param user_id: The pk of the user whose admin page is being rendered.
        :return: Zero, one, or two links to the Neon admin site.
        """
        base_url = settings.NEON_ADMIN_URL.rstrip("/")
        links: list[AdminLink] = []

        account_id = (
            UserProfile.objects.filter(user_id=user_id)
            .values_list("neon_account_id", flat=True)
            .first()
        )
        if account_id:
            links.append(
                {
                    "href": f"{base_url}/accounts/{account_id}/about",
                    "label": "Neon User",
                }
            )

        membership_id = (
            NeonMembership.objects.filter(user_id=user_id)
            .values_list("neon_id", flat=True)
            .first()
        )
        if membership_id:
            links.append(
                {
                    "href": f"{base_url}/memberships/{membership_id}",
                    "label": "Neon Membership",
                }
            )
        return links

    @admin.display(description="Email Confirmed?")
    def get_email_confirmed(self, obj):
        return obj.profile.email_confirmed

    @admin.display(description="Stub Account?")
    def get_stub_account(self, obj):
        return obj.profile.stub_account


@admin.register(EmailFlag)
class EmailFlagAdmin(admin.ModelAdmin):
    search_fields = ("email_address",)
    list_filter = ("flag_type", "notification_subtype")
    list_display = (
        "email_address",
        "id",
        "flag_type",
        "notification_subtype",
        "date_created",
    )
    readonly_fields = (
        "date_modified",
        "date_created",
    )


@admin.register(EmailSent)
class EmailSentAdmin(admin.ModelAdmin):
    search_fields = ("to",)
    list_display = (
        "to",
        "id",
        "subject",
        "date_created",
    )
    readonly_fields = (
        "date_modified",
        "date_created",
    )
    raw_id_fields = ("user",)


@admin.register(FailedEmail)
class FailedEmailAdmin(admin.ModelAdmin):
    search_fields = ("recipient",)
    list_display = (
        "recipient",
        "id",
        "status",
        "date_created",
    )
    readonly_fields = (
        "date_modified",
        "date_created",
    )
    raw_id_fields = ("stored_email",)


class BaseUserEventAdmin(admin.ModelAdmin):
    ordering = ("-pgh_created_at",)
    # Define common attributes to be extended:
    common_list_display = ("get_pgh_created", "get_pgh_label")
    common_list_filters = ("pgh_created_at",)
    common_search_fields = ("pgh_obj",)
    # Default to common attributes:
    list_display = common_list_display
    list_filter = common_list_filters
    search_fields = common_search_fields

    @admin.display(ordering="pgh_created_at", description="Event triggered")
    def get_pgh_created(self, obj):
        return obj.pgh_created_at

    @admin.display(ordering="pgh_label", description="Event label")
    def get_pgh_label(self, obj):
        return obj.pgh_label

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.get_fields()]


@admin.register(UserProxyEvent)
class UserProxyEventAdmin(BaseUserEventAdmin):
    search_help_text = "Search UserProxyEvents by pgh_obj, email, or username."
    search_fields = BaseUserEventAdmin.common_search_fields + (
        "email",
        "username",
    )
    list_display = BaseUserEventAdmin.list_display + (
        "email",
        "username",
    )


@admin.register(UserProfileEvent)
class UserProfileEventAdmin(BaseUserEventAdmin):
    search_help_text = "Search UserProxyEvents by pgh_obj or username."
    search_fields = BaseUserEventAdmin.common_search_fields + (
        "user__username",
    )
    list_display = BaseUserEventAdmin.common_list_display + (
        "user",
        "email_confirmed",
    )
    list_filter = BaseUserEventAdmin.common_list_filters + ("email_confirmed",)


admin.site.register(BarMembership)
admin.site.register(Permission)
