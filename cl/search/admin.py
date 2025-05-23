from admin_cursor_paginator import CursorPaginatorAdmin
from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest

from cl.alerts.models import DocketAlert
from cl.lib.admin import build_admin_url
from cl.lib.cloud_front import invalidate_cloudfront
from cl.lib.models import THUMBNAIL_STATUSES
from cl.lib.string_utils import trunc
from cl.recap.management.commands.delete_document_from_ia import delete_from_ia
from cl.search.models import (
    BankruptcyInformation,
    Citation,
    Claim,
    ClaimHistory,
    Court,
    Courthouse,
    Docket,
    DocketEntry,
    Opinion,
    OpinionCluster,
    OpinionsCited,
    OriginatingCourtInformation,
    Parenthetical,
    ParentheticalGroup,
    RECAPDocument,
    SearchQuery,
)


@admin.register(Opinion)
class OpinionAdmin(CursorPaginatorAdmin):
    raw_id_fields = (
        "cluster",
        "author",
        "joined_by",
    )
    search_fields = (
        "plain_text",
        "html",
        "html_lawbox",
        "html_columbia",
    )
    readonly_fields = (
        "date_created",
        "date_modified",
    )


@admin.register(Citation)
class CitationAdmin(CursorPaginatorAdmin):
    raw_id_fields = ("cluster",)
    list_display = (
        "__str__",
        "type",
    )
    list_filter = ("type",)
    search_fields = (
        "volume",
        "reporter",
        "page",
    )


class CitationInline(admin.TabularInline):
    model = Citation
    extra = 1


@admin.register(OpinionCluster)
class OpinionClusterAdmin(CursorPaginatorAdmin):
    prepopulated_fields = {"slug": ["case_name"]}
    inlines = (CitationInline,)
    raw_id_fields = (
        "docket",
        "panel",
        "non_participating_judges",
    )
    list_filter = (
        "source",
        "blocked",
    )
    readonly_fields = (
        "citation_count",
        "date_modified",
        "date_created",
    )


@admin.register(Court)
class CourtAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "short_name",
        "position",
        "in_use",
        "pk",
        "jurisdiction",
    )
    list_filter = (
        "jurisdiction",
        "in_use",
    )
    search_fields = (
        "full_name",
        "short_name",
        "id",
    )
    readonly_fields = ("date_modified",)


@admin.register(Courthouse)
class CourthouseAdmin(admin.ModelAdmin):
    list_display = (
        "court",
        "building_name",
        "state",
        "country_code",
    )
    search_fields = ("court", "state", "country_code")
    list_filter = (
        "state",
        "country_code",
    )


class ClaimHistoryInline(admin.StackedInline):
    model = ClaimHistory
    extra = 1


@admin.register(Claim)
class ClaimAdmin(CursorPaginatorAdmin):
    raw_id_fields = ("docket", "tags")

    inlines = (ClaimHistoryInline,)


class BankruptcyInformationInline(admin.StackedInline):
    model = BankruptcyInformation


@admin.register(BankruptcyInformation)
class BankruptcyInformationAdmin(admin.ModelAdmin):
    raw_id_fields = ("docket",)


@admin.register(RECAPDocument)
class RECAPDocumentAdmin(CursorPaginatorAdmin):
    search_fields = ("pk__exact",)
    raw_id_fields = ("docket_entry", "tags")
    readonly_fields = (
        "date_created",
        "date_modified",
    )
    actions = ("seal_documents",)

    @admin.action(description="Seal Document")
    def seal_documents(self, request: HttpRequest, queryset: QuerySet) -> None:
        ia_failures = []
        deleted_filepaths = []
        for rd in queryset:
            # Thumbnail
            if rd.thumbnail:
                deleted_filepaths.append(rd.thumbnail.name)
                rd.thumbnail.delete()

            # PDF
            if rd.filepath_local:
                deleted_filepaths.append(rd.filepath_local.name)
                rd.filepath_local.delete()

            # Internet Archive
            if rd.filepath_ia:
                url = rd.filepath_ia
                r = delete_from_ia(url)
                if not r.ok:
                    ia_failures.append(url)

            # Clean up other fields and call save()
            # Important to use save() to ensure these changes are updated in ES
            rd.date_upload = None
            rd.is_available = False
            rd.is_sealed = True
            rd.sha1 = ""
            rd.page_count = None
            rd.file_size = None
            rd.ia_upload_failure_count = None
            rd.filepath_ia = ""
            rd.thumbnail_status = THUMBNAIL_STATUSES.NEEDED
            rd.plain_text = ""
            rd.ocr_status = None
            rd.save()

        # Do a CloudFront invalidation
        invalidate_cloudfront([f"/{path}" for path in deleted_filepaths])

        if ia_failures:
            self.message_user(
                request,
                f"Failed to remove {len(ia_failures)} item(s) from Internet "
                "Archive. Please do so by hand. Sorry. The URL(s): "
                f"{ia_failures}.",
            )
        else:
            self.message_user(
                request,
                f"Successfully sealed and removed {queryset.count()} "
                "document(s).",
            )


class RECAPDocumentInline(admin.StackedInline):
    model = RECAPDocument
    extra = 1

    readonly_fields = (
        "date_created",
        "date_modified",
    )
    raw_id_fields = ("tags",)


@admin.register(DocketEntry)
class DocketEntryAdmin(CursorPaginatorAdmin):
    inlines = (RECAPDocumentInline,)
    search_help_text = (
        "Search DocketEntries by Docket ID or RECAP sequence number."
    )
    search_fields = (
        "docket__id",
        "recap_sequence_number",
    )
    list_display = (
        "get_pk",
        "get_trunc_description",
        "date_filed",
        "time_filed",
        "entry_number",
        "recap_sequence_number",
        "pacer_sequence_number",
    )
    raw_id_fields = ("docket", "tags")
    readonly_fields = (
        "date_created",
        "date_modified",
    )
    list_filter = ("date_filed", "date_created", "date_modified")

    @admin.display(description="Docket entry")
    def get_pk(self, obj):
        return obj.pk

    @admin.display(description="Description")
    def get_trunc_description(self, obj):
        return trunc(obj.description, 35, ellipsis="...")


@admin.register(OriginatingCourtInformation)
class OriginatingCourtInformationAdmin(admin.ModelAdmin):
    raw_id_fields = (
        "assigned_to",
        "ordering_judge",
    )


@admin.register(Docket)
class DocketAdmin(CursorPaginatorAdmin):
    change_form_template = "admin/docket_change_form.html"
    prepopulated_fields = {"slug": ["case_name"]}
    list_display = (
        "__str__",
        "pacer_case_id",
        "docket_number",
    )
    search_help_text = "Search dockets by PK, PACER case ID, or Docket number."
    search_fields = ("pk", "pacer_case_id", "docket_number")
    inlines = (BankruptcyInformationInline,)
    readonly_fields = (
        "date_created",
        "date_modified",
        "view_count",
    )
    autocomplete_fields = (
        "court",
        "appeal_from",
    )
    raw_id_fields = (
        "panel",
        "tags",
        "assigned_to",
        "referred_to",
        "originating_court_information",
        "idb_data",
        "parent_docket",
    )

    def change_view(self, request, object_id, form_url="", extra_context=None):
        """Add links to pre-filtered related admin pages."""
        extra_context = extra_context or {}
        query_params = {"docket": object_id}

        extra_context["docket_entries_url"] = build_admin_url(
            DocketEntry,
            query_params,
        )

        extra_context["docket_alerts_url"] = build_admin_url(
            DocketAlert,
            query_params,
        )

        return super().change_view(
            request, object_id, form_url, extra_context=extra_context
        )


@admin.register(OpinionsCited)
class OpinionsCitedAdmin(CursorPaginatorAdmin):
    raw_id_fields = (
        "citing_opinion",
        "cited_opinion",
    )
    search_fields = ("=citing_opinion__id",)


@admin.register(Parenthetical)
class ParentheticalAdmin(CursorPaginatorAdmin):
    raw_id_fields = (
        "describing_opinion",
        "described_opinion",
        "group",
    )
    search_fields = ("=describing_opinion__id",)


@admin.register(ParentheticalGroup)
class ParentheticalGroupAdmin(CursorPaginatorAdmin):
    raw_id_fields = (
        "opinion",
        "representative",
    )


@admin.register(SearchQuery)
class SearchQueryAdmin(CursorPaginatorAdmin):
    raw_id_fields = ("user",)
    list_display = ("__str__", "engine", "source")
    list_filter = ("engine", "source")
    search_fields = ("user__username",)
