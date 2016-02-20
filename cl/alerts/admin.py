from django.contrib import admin
from cl.alerts.models import Alert, RealTimeQueue


class AlertAdmin(admin.ModelAdmin):
    list_filter = (
        'rate',
        'always_send_email',
    )
    list_display = (
        'name',
        'id',
        'rate',
        'always_send_email',
        'date_last_hit',
    )
    raw_id_fields = (
        'user',
    )


class AlertInline(admin.TabularInline):
    model = Alert
    extra = 1


class RealTimeQueueAdmin(admin.ModelAdmin):
    list_filter = ('item_type',)
    list_display = (
        '__str__',
        'item_type',
        'item_pk',
    )
    readonly_fields = (
        'date_modified',
    )

admin.site.register(Alert, AlertAdmin)
admin.site.register(RealTimeQueue, RealTimeQueueAdmin)
