from django.contrib import admin
from django.contrib.auth.models import User
from cl.alerts.admin import AlertInline
from cl.donate.admin import DonationInline
from cl.favorites.admin import FavoriteInline
from cl.users.models import UserProfile


def get_email_confirmed(obj):
    return obj.profile.email_confirmed
get_email_confirmed.short_description = "Email Confirmed?"


def get_stub_account(obj):
    return obj.profile.stub_account
get_stub_account.short_description = "Stub Account?"


class UserProfileInline(admin.StackedInline):
    model = UserProfile

class UserAdmin(admin.ModelAdmin):
    inlines = (
        UserProfileInline,
        AlertInline,
        DonationInline,
        FavoriteInline,
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
