from django.contrib import admin
from django.contrib.auth.models import User
from alert.userHandling.models import *


def get_email_confirmed(obj):
    return obj.get_profile().email_confirmed
get_email_confirmed.short_description = "Email Confirmed?"


def get_stub_account(obj):
    return obj.get_profile().stub_account
get_stub_account.short_description = "Stub Account?"


class UserProfileInline(admin.StackedInline):
    model = UserProfile


class UserAdmin(admin.ModelAdmin):
    inlines = [UserProfileInline, ]
    list_display = ('username', get_email_confirmed, get_stub_account)


class FavoriteAdmin(admin.ModelAdmin):
    raw_id_fields = ("doc_id",)


admin.site.register(Alert)
admin.site.register(BarMembership)
admin.site.register(Favorite, FavoriteAdmin)

# Un-register the built in user admin and register the custom User admin with UserProfile
admin.site.unregister(User)
admin.site.register(User, UserAdmin)
