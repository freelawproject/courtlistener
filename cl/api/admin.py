from django.contrib import admin

from cl.api.models import Webhook, WebhookEvent


@admin.register(Webhook)
class WebhookAdmin(admin.ModelAdmin):
    raw_id_fields = ("user",)
    list_display = (
        "__str__",
        "enabled",
        "get_event_type_display",
        "version",
        "failure_count",
    )
    list_filter = (
        "enabled",
        "event_type",
        "version",
        "failure_count",
    )
    readonly_fields = (
        "date_created",
        "date_modified",
    )


@admin.register(WebhookEvent)
class WebhookEvent(admin.ModelAdmin):
    list_display = (
        "__str__",
        "webhook",
        "status_code",
    )
    list_filter = ("status_code",)
    readonly_fields = (
        "date_created",
        "date_modified",
    )
