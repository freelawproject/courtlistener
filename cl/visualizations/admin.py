"""Django admin configuration for SCOTUS network visualizations."""

from django.contrib import admin

from cl.visualizations.models import JSONVersion, SCOTUSMap


@admin.register(JSONVersion)
class JSONVersionAdmin(admin.ModelAdmin):
    """Admin for visualization JSON versions."""

    readonly_fields = (
        "date_created",
        "date_modified",
    )
    raw_id_fields = ("map",)


class JSONVersionInline(admin.StackedInline):
    """Inline for editing a visualization's JSON versions."""

    model = JSONVersion
    extra = 1


@admin.register(SCOTUSMap)
class SCOTUSMapAdmin(admin.ModelAdmin):
    """Admin for SCOTUS network visualizations, with their JSON versions inline."""

    inlines = (JSONVersionInline,)
    raw_id_fields = (
        "clusters",
        "cluster_start",
        "cluster_end",
    )
    readonly_fields = (
        "date_created",
        "date_modified",
        "generation_time",
    )
    list_display = (
        "__str__",
        "user_id",
        "date_created",
        "date_modified",
        "view_count",
        "published",
        "deleted",
    )
    list_filter = (
        "published",
        "deleted",
    )
    autocomplete_fields = ("user",)
    search_fields = (
        "id",
        "title",
    )
