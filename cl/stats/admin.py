from django.contrib import admin

from cl.stats.models import Event, Stat


@admin.register(Stat)
class StatAdmin(admin.ModelAdmin):
    fields = ("name", "date_logged", "count")


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("__str__", "user", "date_created", "description")
    list_filter = ("user",)
    readonly_fields = ("date_created",)
    date_hierarchy = "date_created"
    ordering = ("-date_created",)
    search_fields = ("id", "description", "user__username")
