from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from cl.ai.models import LLMRequest, LLMTask, Prompt


@admin.register(Prompt)
class PromptAdmin(admin.ModelAdmin):
    list_display = (
        "prompt_details_link",
        "is_active",
        "date_created",
        "date_modified",
    )
    list_display_links = ("prompt_details_link",)
    list_filter = ("prompt_type", "is_active")
    search_fields = ("name", "text", "notes")
    readonly_fields = ("date_created", "date_modified")

    @admin.display(description="Prompt", ordering="id")
    def prompt_details_link(self, obj):
        return str(obj)


class LLMTaskInline(admin.TabularInline):
    """Inline to display related LLMTask objects in LLMRequest admin."""

    model = LLMTask
    extra = 0
    can_delete = False
    show_change_link = True
    fields = (
        "status",
        "llm_key",
        "task_type",
        "error_message",
        "date_created",
    )
    readonly_fields = (
        "status",
        "llm_key",
        "task_type",
        "error_message",
        "date_created",
    )

    def has_add_permission(self, request, obj=None):
        """Disable adding tasks from the inline."""
        return False


@admin.register(LLMRequest)
class LLMRequestAdmin(admin.ModelAdmin):
    list_display = (
        "request_details_link",
        "is_batch",
        "batch_id",
        "provider",
        "api_model_name",
        "total_tasks",
        "completed_tasks",
        "failed_tasks",
        "date_created",
    )
    list_display_links = ("request_details_link",)
    list_filter = ("provider", "status", "is_batch", "api_model_name")
    search_fields = ("name", "batch_id")
    readonly_fields = ("date_created", "date_modified")
    filter_horizontal = ("prompts",)
    inlines = [LLMTaskInline]

    @admin.display(description="Request", ordering="id")
    def request_details_link(self, obj):
        return str(obj)


@admin.register(LLMTask)
class LLMTaskAdmin(admin.ModelAdmin):
    list_display = (
        "task_details_link",
        "status",
        "get_provider",
        "retry_count",
        "request",
        "link_to_target_object",
        "date_created",
    )
    list_display_links = ("task_details_link",)

    list_filter = ("status", "request__provider", "content_type")
    search_fields = ("error_message",)
    readonly_fields = (
        "date_created",
        "date_modified",
        "date_started",
        "date_completed",
        "processing_time_ms",
        "link_to_target_object_detail",
    )
    raw_id_fields = ("request",)

    @admin.display(description="Task", ordering="id")
    def task_details_link(self, obj):
        return str(obj)

    @admin.display(description="Provider", ordering="request__provider")
    def get_provider(self, obj):
        if obj.request:
            return obj.request.get_provider_display()
        return None

    def link_to_target_object(self, obj):
        """Creates a link to the Generic Foreign Key object in the list view"""
        if obj.content_object:
            content_type = obj.content_type
            admin_url_name = (
                f"admin:{content_type.app_label}_{content_type.model}_change"
            )
            url = reverse(admin_url_name, args=[obj.object_id])
            return format_html(
                '<a href="{}">{}</a>',
                url,
                obj.content_object,
            )
        return "-"

    link_to_target_object.short_description = "Target Object"

    def link_to_target_object_detail(self, obj):
        """Creates a link to the Generic Foreign Key object in the Detail/Edit view"""
        return self.link_to_target_object(obj)

    link_to_target_object_detail.short_description = "View Target Object"
