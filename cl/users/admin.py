from django.contrib import admin
from django.contrib.auth.models import Permission, User
from rest_framework.authtoken.models import Token

from cl.alerts.admin import AlertInline, DocketAlertInline
from cl.donate.admin import DonationInline, MonthlyDonationInline
from cl.favorites.admin import FavoriteInline, UserTagInline
from cl.lib.admin import AdminTweaksMixin
from cl.users.models import (
    BackoffEvent,
    BarMembership,
    EmailFlag,
    EmailSent,
    UserProfile,
)


def get_email_confirmed(obj):
    return obj.profile.email_confirmed


get_email_confirmed.short_description = "Email Confirmed?"


def get_stub_account(obj):
    return obj.profile.stub_account


get_stub_account.short_description = "Stub Account?"


class TokenInline(admin.StackedInline):
    model = Token


class UserProfileInline(admin.StackedInline):
    model = UserProfile


class UserAdmin(admin.ModelAdmin, AdminTweaksMixin):
    inlines = (
        UserProfileInline,
        DonationInline,
        MonthlyDonationInline,
        AlertInline,
        DocketAlertInline,
        FavoriteInline,
        UserTagInline,
        TokenInline,
    )
    list_display = (
        "username",
        get_email_confirmed,
        get_stub_account,
    )
    search_fields = (
        "username",
        "first_name",
        "last_name",
        "email",
    )


@admin.register(EmailFlag)
class EmailFlagAdmin(admin.ModelAdmin):
    search_fields = ("email_address",)
    list_filter = ("object_type", "event_sub_type", "flag")
    list_display = (
        "email_address",
        "id",
        "object_type",
        "event_sub_type",
        "flag",
        "date_created",
    )


@admin.register(BackoffEvent)
class BackoffEventAdmin(admin.ModelAdmin):
    search_fields = ("email_address",)
    list_display = (
        "email_address",
        "id",
        "retry_counter",
        "notification_subtype",
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
    raw_id_fields = ("user",)


# Replace the normal User admin with our better one.
admin.site.unregister(User)
admin.site.register(User, UserAdmin)
admin.site.register(BarMembership)
admin.site.register(Permission)
