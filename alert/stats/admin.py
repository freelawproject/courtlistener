from alert.stats.models import Stat

from django.contrib import admin


class StatAdmin(admin.ModelAdmin):
    fields = ('name', 'date_logged', 'count')

admin.site.register(Stat, StatAdmin)

