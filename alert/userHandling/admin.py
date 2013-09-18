from django.contrib import admin
from django.contrib.auth.models import User
from alert.userHandling.models import *


def getEmailConfirmed(obj):
    return obj.get_profile().email_confirmed
getEmailConfirmed.short_description = "Email Confirmed?"


class UserProfileInline(admin.StackedInline):
    model = UserProfile

class UserAdmin(admin.ModelAdmin):
    inlines = [UserProfileInline, ]
    list_display = ('username', getEmailConfirmed)

class DocumentAdmin(admin.ModelAdmin):
    # ordering is brutal on MySQL. Don't put it here. Sorry.
    #list_display = ('citation',)
    #list_filter = ('court',)
    fields = ('source', 'sha1', 'date_filed', 'court',
              'excerptSummary', 'download_URL',
              'local_path', 'plain_text', 'html',
              'precedential_status',)
    search_fields = ['@plain_text']


class FavoriteAdmin(admin.ModelAdmin):
    raw_id_fields = ("doc_id",)


admin.site.register(Alert)
admin.site.register(BarMembership)
admin.site.register(Favorite, FavoriteAdmin)

# Unregister the built in user admin and register the custom User admin with UserProfile
admin.site.unregister(User)
admin.site.register(User, UserAdmin)
