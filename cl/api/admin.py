from django import forms
from django.contrib import admin

from cl.api.models import APIThrottle, Webhook, WebhookEvent


class APIThrottleInlineForm(forms.ModelForm):
    """Inline form for User admin that prevents editing MEMBERSHIP throttles.

    Django admin inlines call `get_readonly_fields(request, obj)` with the
    parent object (User), not the inline instance, so that hook can't be used
    for per-row control. Instead, we disable fields when the instance comes
    from a MEMBERSHIP source, making them read-only in the UI and ignoring
    any submitted changes.
    """

    class Meta:
        model = APIThrottle
        fields = ("user", "throttle_type", "rate", "source", "notes")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        instance = self.instance
        if (
            instance
            and instance.pk
            and instance.source == APIThrottle.Source.MEMBERSHIP
        ):
            for field in self.fields.values():
                field.disabled = True


@admin.register(APIThrottle)
class APIThrottleAdmin(admin.ModelAdmin):
    raw_id_fields = ("user",)
    list_display = (
        "user",
        "throttle_type",
        "rate",
        "source",
        "date_created",
    )
    list_filter = ("throttle_type", "source")
    search_fields = (
        "user__username",
        "user__email",
        "user__pk",
    )
    readonly_fields = (
        "date_created",
        "date_modified",
    )

    def get_readonly_fields(self, request, obj=None):
        """Lock MEMBERSHIP rows from edits.

        These are owned by the Neon webhook handlers and editing them
        in admin would silently get overwritten by the next webhook.
        """
        base = super().get_readonly_fields(request, obj)
        if obj and obj.source == APIThrottle.Source.MEMBERSHIP:
            return tuple(base) + (
                "user",
                "throttle_type",
                "rate",
                "blocked",
                "source",
                "notes",
            )
        return base


class APIThrottleInline(admin.TabularInline):
    model = APIThrottle
    extra = 0
    raw_id_fields = ("user",)
    form = APIThrottleInlineForm
    fields = ("user", "throttle_type", "rate", "source", "notes")


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
