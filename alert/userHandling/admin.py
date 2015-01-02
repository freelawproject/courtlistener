from django.contrib import admin
from django.contrib.auth.models import User
from alert.userHandling.models import UserProfile


def get_email_confirmed(obj):
    return obj.profile.email_confirmed
get_email_confirmed.short_description = "Email Confirmed?"


def get_stub_account(obj):
    return obj.profile.stub_account
get_stub_account.short_description = "Stub Account?"


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    filter_horizontal = (
        'donation',
        'favorite',
        'alert',
    )


class UserAdmin(admin.ModelAdmin):
    inlines = (
        UserProfileInline,
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
