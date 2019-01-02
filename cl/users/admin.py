from django.contrib import admin
from django.contrib.auth.models import Permission, User
from rest_framework.authtoken.models import Token

from cl.alerts.admin import AlertInline, DocketAlertInline
from cl.donate.admin import DonationInline, MonthlyDonationInline
from cl.favorites.admin import FavoriteInline
from cl.lib.admin import CSSAdminMixin
from cl.users.models import UserProfile, BarMembership


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


class UserAdmin(admin.ModelAdmin, CSSAdminMixin):
    inlines = (
        UserProfileInline,
        DonationInline,
        MonthlyDonationInline,
        AlertInline,
        DocketAlertInline,
        FavoriteInline,
        TokenInline,
    )
    list_display = (
        'username',
        get_email_confirmed,
        get_stub_account,
    )
    search_fields = (
        'username',
        'first_name',
        'last_name',
        'email',
    )


# Replace the normal User admin with our better one.
admin.site.unregister(User)
admin.site.register(User, UserAdmin)
admin.site.register(BarMembership)
admin.site.register(Permission)
