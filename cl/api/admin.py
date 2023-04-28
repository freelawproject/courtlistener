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
    )
    readonly_fields = (
        "date_created",
        "date_modified",
    )


class WebhookInline(admin.TabularInline):
    model = Webhook


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    raw_id_fields = ("webhook",)
    list_display = (
        "__str__",
        "webhook",
        "date_created",
        "next_retry_date",
        "event_status",
        "status_code",
    )
    list_filter = (
        "debug",
        "status_code",
    )
    readonly_fields = (
        "date_created",
        "date_modified",
    )
