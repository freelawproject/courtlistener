from cl.visualizations.models import SCOTUSMap, JSONVersion
from django.contrib import admin


class JSONVersionAdmin(admin.ModelAdmin):
    readonly_fields = (
        'date_created',
        'date_modified',
    )
    raw_id_fields = (
        'map',
    )


class JSONVersionInline(admin.StackedInline):
    model = JSONVersion
    extra = 1


class SCOTUSMapAdmin(admin.ModelAdmin):
    inlines = (
        JSONVersionInline,
    )
    raw_id_fields = (
        'clusters',
        'cluster_start',
        'cluster_end',
    )
    readonly_fields = (
        'date_created',
        'date_modified',
        'date_published',
        'generation_time',
    )
    list_display = (
        '__unicode__',
        'user_id',
        'date_created',
        'date_modified',
        'view_count',
        'published',
        'deleted',
    )
    list_filter = (
        'published',
        'deleted',
    )


admin.site.register(SCOTUSMap, SCOTUSMapAdmin)
admin.site.register(JSONVersion, JSONVersionAdmin)
