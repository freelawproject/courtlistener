from typing import cast

from django.apps import apps
from django.contrib import admin
from django.contrib.auth.forms import UserChangeForm
from django.contrib.auth.models import Permission, User
from django.db.models import Model
from rest_framework.authtoken.models import Token

from cl.alerts.admin import AlertInline, DocketAlertInline
from cl.api.admin import APIThrottleInline, WebhookInline
from cl.donate.admin import (
    DonationInline,
    MonthlyDonationInline,
    NeonMembershipInline,
)
from cl.favorites.admin import NoteInline, PrayerInline, UserTagInline
from cl.favorites.models import UserTag
from cl.lib.admin import (
    AdminLinkConfig,
    AdminTweaksMixin,
    generate_admin_links,
)
from cl.lib.redis_utils import get_redis_interface
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
    change_form_template = "admin/user_change_form.html"
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

    def api_calls_count(self, obj):
        r = get_redis_interface("STATS")
        total = 0
        for api_prefix in ["v3", "v4"]:
            count = r.zscore(f"api:{api_prefix}.user.counts", obj.id)
            if count:
                total += int(count)
        return total

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

        extra_context["custom_links"] = generate_admin_links(custom_links)

        return super().change_view(
            request, object_id, form_url, extra_context=extra_context
        )

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
