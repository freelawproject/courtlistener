from django.contrib import admin

from cl.api.models import APIThrottle, Webhook, WebhookEvent


@admin.register(APIThrottle)
class APIThrottleAdmin(admin.ModelAdmin):
    raw_id_fields = ("user",)
    list_display = (
        "user",
        "throttle_type",
        "blocked",
        "rate",
        "date_created",
    )
    list_filter = (
        "throttle_type",
        "blocked",
    )
    search_fields = (
        "user__username",
        "user__email",
        "user__pk",
    )
    readonly_fields = (
        "date_created",
        "date_modified",
    )


class APIThrottleInline(admin.TabularInline):
    model = APIThrottle
    extra = 0
    raw_id_fields = ("user",)


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
    extra = 1


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
