from django.contrib import admin

from cl.alerts.models import (
    Alert,
    DocketAlert,
    ParentAlert,
    RealTimeQueue,
    ScheduledAlertHit,
    UserRateAlert,
)


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_filter = ("rate",)
    list_display = (
        "name",
        "id",
        "rate",
        "date_last_hit",
    )
    raw_id_fields = ("user",)


class AlertInline(admin.TabularInline):
    model = Alert
    extra = 1


@admin.register(DocketAlert)
class DocketAlertAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "user",
        "docket",
        "date_created",
    )
    raw_id_fields = (
        "docket",
        "user",
    )
    readonly_fields = ("date_created", "date_modified")


class DocketAlertInline(admin.TabularInline):
    model = DocketAlert
    extra = 1

    raw_id_fields = (
        "user",
        "docket",
    )


@admin.register(RealTimeQueue)
class RealTimeQueueAdmin(admin.ModelAdmin):
    list_filter = ("item_type",)
    list_display = (
        "__str__",
        "item_type",
        "item_pk",
    )
    readonly_fields = ("date_modified",)


class ParentAlertInline(admin.TabularInline):
    model = ParentAlert
    extra = 0


@admin.register(UserRateAlert)
class UserRateAlertAdmin(admin.ModelAdmin):
    inlines = (ParentAlertInline,)
    list_filter = ("rate",)
    list_display = (
        "id",
        "user",
        "rate",
        "date_created",
    )
    raw_id_fields = ("user",)


class ScheduledAlertHitInline(admin.TabularInline):
    model = ScheduledAlertHit
    extra = 0


@admin.register(ParentAlert)
class ParentAlertAdmin(admin.ModelAdmin):
    inlines = (ScheduledAlertHitInline,)
    list_display = (
        "id",
        "alert",
        "user_rate",
        "date_created",
    )
    raw_id_fields = ("alert", "user_rate")


@admin.register(ScheduledAlertHit)
class ScheduledAlertHitAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "parent_alert",
        "date_created",
    )
    raw_id_fields = ("parent_alert",)
