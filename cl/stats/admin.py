from django.contrib import admin

from cl.stats.models import Stat, Event


@admin.register(Stat)
class StatAdmin(admin.ModelAdmin):
    fields = ('name', 'date_logged', 'count')


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'date_created', 'description')
    date_hierarchy = 'date_created'
    ordering = ('-date_created',)
    search_fields = ('id', 'description')
