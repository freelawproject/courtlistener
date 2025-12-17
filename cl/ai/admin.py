from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import LLMConfig, LLMPromptSet, LLMRun, LLMTask, Prompt


@admin.register(Prompt)
class PromptAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "role",
        "position",
        "short_text",
        "date_created",
    )
    list_filter = ("role", "date_created")
    search_fields = ("text", "name")
    ordering = ("name",)

    def short_text(self, obj):
        return obj.text[:80] + "..." if len(obj.text) > 80 else obj.text

    short_text.short_description = "Prompt Text"


@admin.register(LLMConfig)
class LLMConfigAdmin(admin.ModelAdmin):
    list_display = ("name", "provider", "model_name", "date_created")
    list_filter = ("provider", "model_name")
    search_fields = ("name", "model_name")


@admin.register(LLMPromptSet)
class LLMPromptSetAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "version",
        "count_prompts",
        "date_created",
    )
    list_filter = ("name", "date_created")
    search_fields = ("name", "description")

    autocomplete_fields = ["prompts"]

    # adds "Save as new" button to the edit page for versioning
    save_as = True

    def count_prompts(self, obj):
        return obj.prompts.count()

    count_prompts.short_description = "# Prompts"


@admin.register(LLMRun)
class LLMRunAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "success",
        "llm_config",
        "prompt_set",
        "link_to_target_object",
        "date_created",
    )
    list_filter = ("success", "llm_config__name")
    search_fields = ("prompt_set__name", "llm_config__name")

    readonly_fields = (
        "llm_config",
        "prompt_set",
        "output",
        "success",
        "content_type",
        "object_id",
        "link_to_target_object_detail",
    )

    def has_add_permission(self, request):
        """Removes the 'Add' button"""
        return False

    def has_change_permission(self, request, obj=None):
        """Removes the 'Save' buttons and makes the form read-only, users can still view the details if they have the 'view' permission"""
        return False

    def link_to_target_object(self, obj):
        """Creates a link to the Generic Foreign Key object in the list view"""
        if obj.content_object:
            # build the admin url: admin:app_label_modelname_change
            content_type = obj.content_type
            admin_url_name = (
                f"admin:{content_type.app_label}_{content_type.model}_change"
            )
            url = reverse(admin_url_name, args=[obj.object_id])
            return format_html(
                '<a href="{}">{} ({})</a>',
                url,
                obj.content_object,
                obj.object_id,
            )
        return "-"

    link_to_target_object.short_description = "Target Object"

    def link_to_target_object_detail(self, obj):
        """Creates a link to the Generic Foreign Key object in the Detail/Edit view"""
        return self.link_to_target_object(obj)

    link_to_target_object_detail.short_description = "View Target Object"


@admin.register(LLMTask)
class LLMTaskAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "get_provider",
        "get_model",
        "get_version",
        "date_modified",
    )
    search_fields = ("name",)
    list_filter = ("current_config__provider", "current_config__model_name")

    autocomplete_fields = ["current_config", "current_prompt_set"]

    @admin.display(description="Current Provider")
    def get_provider(self, obj):
        return obj.current_config.provider

    @admin.display(description="Current Model")
    def get_model(self, obj):
        return obj.current_config.model_name

    @admin.display(description="Current Prompt Version")
    def get_version(self, obj):
        return f"v{obj.current_prompt_set.version}"

    def get_readonly_fields(self, request, obj=None):
        """Only allow to set name when creating object"""
        if obj:
            return self.readonly_fields + ("name",)
        return self.readonly_fields
