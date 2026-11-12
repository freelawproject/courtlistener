"""Django admin configuration for search alerts, docket alerts, and scheduled hits."""

from django.contrib import admin

from cl.alerts.models import (
    Alert,
    DocketAlert,
    ScheduledAlertHit,
)


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    """Admin for search alerts."""

    list_filter = ("rate",)
    list_display = (
        "name",
        "id",
        "rate",
        "date_last_hit",
    )
    raw_id_fields = ("user",)


class AlertInline(admin.TabularInline):
    """Inline for editing search alerts on a parent object's admin page."""

    model = Alert
    extra = 1


@admin.register(DocketAlert)
class DocketAlertAdmin(admin.ModelAdmin):
    """Admin for docket alerts."""

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
    """Inline for editing docket alerts on a parent object's admin page."""

    model = DocketAlert
    extra = 1

    raw_id_fields = (
        "user",
        "docket",
    )


@admin.register(ScheduledAlertHit)
class ScheduledAlertHitAdmin(admin.ModelAdmin):
    """Admin for search alert hits awaiting a scheduled email."""

    list_display = (
        "id",
        "user",
        "alert_rate",
        "hit_status",
        "date_created",
    )
    raw_id_fields = (
        "alert",
        "user",
    )

    def alert_rate(self, obj):
        """Display the rate of the hit's alert."""
        return obj.alert.rate
