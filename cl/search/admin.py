from django.contrib import admin

from cl.search.models import (
    Citation, Court, Docket, DocketEntry, Opinion, OpinionCluster,
    OpinionsCited, OriginatingCourtInformation, RECAPDocument,
)


@admin.register(Opinion)
class OpinionAdmin(admin.ModelAdmin):
    fields = (
        'cluster',
        'author',
        'author_str',
        'per_curiam',
        'joined_by',
        'type',
        'sha1',
        'download_url',
        'local_path',
        'extracted_by_ocr',
        'plain_text',
        'html',
        'html_lawbox',
        'html_columbia',
        'html_with_citations',
        'date_created',
        'date_modified',
    )
    raw_id_fields = (
        'cluster',
        'author',
        'joined_by',
    )
    search_fields = (
        'plain_text',
        'html',
        'html_lawbox',
        'html_columbia',
    )
    readonly_fields = (
        'date_created',
        'date_modified',
    )

    def save_model(self, request, obj, form, change):
        obj.save()
        from cl.search.tasks import add_or_update_opinions
        add_or_update_opinions.delay([obj.pk])

    def delete_model(self, request, obj):
        obj.delete()
        from cl.search.tasks import delete_items
        delete_items.delay([obj.pk], 'opinions')


@admin.register(OpinionCluster)
class OpinionClusterAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ['case_name']}
    raw_id_fields = (
        'docket',
        'panel',
        'non_participating_judges',
    )
    list_filter = (
        'source',
        'blocked',
    )
    readonly_fields = (
        'citation_count',
        'date_modified',
        'date_created',
    )

    def save_model(self, request, obj, form, change):
        obj.save()
        from cl.search.tasks import add_or_update_cluster
        add_or_update_cluster.delay(obj.pk)


@admin.register(Citation)
class CitationAdmin(admin.ModelAdmin):
    raw_id_fields = (
        'cluster',
    )
    list_display = (
        '__unicode__',
        'type',
    )
    list_filter = (
        'type',
    )
    search_fields = (
        'volume',
        'reporter',
        'page',
    )


@admin.register(Court)
class CourtAdmin(admin.ModelAdmin):
    list_display = (
        'full_name',
        'short_name',
        'position',
        'in_use',
        'pk'
    )
    list_filter = (
        'jurisdiction',
        'in_use',
    )
    search_fields = (
        'full_name',
        'short_name',
        'id',
    )
    readonly_fields = (
        'date_modified',
    )


@admin.register(RECAPDocument)
class RECAPDocumentAdmin(admin.ModelAdmin):
    raw_id_fields = (
        'docket_entry',
    )

    readonly_fields = (
        'date_created',
        'date_modified',
    )


class RECAPDocumentInline(admin.StackedInline):
    model = RECAPDocument
    extra = 1

    readonly_fields = (
        'date_created',
        'date_modified',
    )


@admin.register(DocketEntry)
class DocketEntryAdmin(admin.ModelAdmin):
    inlines = (
        RECAPDocumentInline,
    )
    raw_id_fields = (
        'docket',
    )
    readonly_fields = (
        'date_created',
        'date_modified',
    )


class DocketEntryInline(admin.TabularInline):
    model = DocketEntry
    extra = 1


@admin.register(OriginatingCourtInformation)
class OriginatingCourtInformationAdmin(admin.ModelAdmin):
    raw_id_fields = (
        'assigned_to',
        'ordering_judge',
    )


@admin.register(Docket)
class DocketAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ['case_name']}
    inlines = (
        DocketEntryInline,
    )
    readonly_fields = (
        'date_created',
        'date_modified',
        'view_count',
    )
    raw_id_fields = (
        'assigned_to',
        'referred_to',
        'originating_court_information',
    )


@admin.register(OpinionsCited)
class OpinionsCitedAdmin(admin.ModelAdmin):
    raw_id_fields = (
        'citing_opinion',
        'cited_opinion',
    )
    search_fields = (
        '=citing_opinion__id',
    )

    def save_model(self, request, obj, form, change):
        obj.save()
        from cl.search.tasks import add_or_update_opinions
        add_or_update_opinions.delay([obj.citing_opinion_id])
