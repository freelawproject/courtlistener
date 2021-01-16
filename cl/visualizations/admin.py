from django.contrib import admin

from cl.visualizations.models import JSONVersion, Referer, SCOTUSMap


@admin.register(JSONVersion)
class JSONVersionAdmin(admin.ModelAdmin):
    readonly_fields = (
        "date_created",
        "date_modified",
    )
    raw_id_fields = ("map",)


class JSONVersionInline(admin.StackedInline):
    model = JSONVersion
    extra = 1


@admin.register(Referer)
class RefererAdmin(admin.ModelAdmin):
    readonly_fields = (
        "date_created",
        "date_modified",
    )
    raw_id_fields = ("map",)
    list_filter = ("display",)
    list_display = (
        "__str__",
        "display",
        "date_created",
        "date_modified",
    )
    search_fields = (
        "id",
        "url",
        "page_title",
    )


class RefererInline(admin.StackedInline):
    model = Referer
    extra = 1


@admin.register(SCOTUSMap)
class SCOTUSMapAdmin(admin.ModelAdmin):
    inlines = (
        JSONVersionInline,
        RefererInline,
    )
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
    search_fields = (
        "id",
        "title",
    )
