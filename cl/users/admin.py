from django.contrib import admin
from django.contrib.auth.models import Permission, User
from rest_framework.authtoken.models import Token

from cl.alerts.admin import AlertInline, DocketAlertInline
from cl.donate.admin import DonationInline, MonthlyDonationInline
from cl.favorites.admin import NoteInline, UserTagInline
from cl.lib.admin import AdminTweaksMixin
from cl.users.models import (
    BarMembership,
    EmailFlag,
    EmailSent,
    FailedEmail,
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
        NoteInline,
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


# Replace the normal User admin with our better one.
admin.site.unregister(User)
admin.site.register(User, UserAdmin)
admin.site.register(BarMembership)
admin.site.register(Permission)
