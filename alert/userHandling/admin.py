# This software and any associated files are copyright 2010 Brian Carver and
# Michael Lissner.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


from django.contrib import admin
from django.contrib.auth.models import User
from alert.userHandling.models import *


def getEmailConfirmed(obj):
    return obj.get_profile().emailConfirmed
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
    fields = ('source', 'documentSHA1', 'dateFiled', 'court',
              'excerptSummary', 'download_URL',
              'local_path', 'documentPlainText', 'documentHTML',
              'documentType',)
    search_fields = ['@documentPlainText']


class FavoriteAdmin(admin.ModelAdmin):
    raw_id_fields = ("doc_id",)


admin.site.register(Alert)
admin.site.register(BarMembership)
admin.site.register(Favorite, FavoriteAdmin)

# Unregister the built in user admin and register the custom User admin with UserProfile
admin.site.unregister(User)
admin.site.register(User, UserAdmin)
