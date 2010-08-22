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


admin.site.register(Alert)
admin.site.register(BarMembership)

# Unregister the built in user admin and register the custom User admin with UserProfile
admin.site.unregister(User)
admin.site.register(User, UserAdmin)
