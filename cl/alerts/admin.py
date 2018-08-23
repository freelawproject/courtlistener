from django.contrib import admin

from cl.alerts.models import Alert, RealTimeQueue, DocketAlert


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_filter = (
        'rate',
    )
    list_display = (
        'name',
        'id',
        'rate',
        'date_last_hit',
    )
    raw_id_fields = (
        'user',
    )


class AlertInline(admin.TabularInline):
    model = Alert
    extra = 1


@admin.register(DocketAlert)
class DocketAlertAdmin(admin.ModelAdmin):
    list_display = (
        '__str__',
        'user',
        'docket',
        'date_created',
    )
    raw_id_fields = (
        'docket',
        'user',
    )


class DocketAlertInline(admin.TabularInline):
    model = DocketAlert
    extra = 1

    raw_id_fields = (
        'user',
        'docket',
    )

@admin.register(RealTimeQueue)
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
