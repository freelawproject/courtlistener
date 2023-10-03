from admin_cursor_paginator import CursorPaginatorAdmin
from django.contrib import admin
from django.db.models import QuerySet
from django.forms import ModelForm
from django.http import HttpRequest

from cl.alerts.admin import DocketAlertInline
from cl.lib.cloud_front import invalidate_cloudfront
from cl.lib.models import THUMBNAIL_STATUSES
from cl.recap.management.commands.delete_document_from_ia import delete_from_ia
from cl.search.models import (
    BankruptcyInformation,
    Citation,
    Claim,
    ClaimHistory,
    ClusterStub,
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
)
from cl.search.tasks import add_items_to_solr


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

    def save_model(self, request, obj, form, change):
        obj.save()
        from cl.search.tasks import add_items_to_solr

        add_items_to_solr.delay([obj.pk], "search.Opinion")

    def delete_model(self, request, obj):
        obj.delete()
        from cl.search.tasks import delete_items

        delete_items.delay([obj.pk], "search.Opinion")


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

    def save_model(self, request, obj, form, change):
        obj.save()
        from cl.search.tasks import add_items_to_solr

        add_items_to_solr.delay([obj.pk], "search.OpinionCluster")


@admin.register(Court)
class CourtAdmin(admin.ModelAdmin):
    list_display = ("full_name", "short_name", "position", "in_use", "pk")
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
            url = rd.filepath_ia
            r = delete_from_ia(url)
            if not r.ok:
                ia_failures.append(url)

        queryset.update(
            date_upload=None,
            is_available=False,
            is_sealed=True,
            sha1="",
            page_count=None,
            file_size=None,
            ia_upload_failure_count=None,
            filepath_ia="",
            thumbnail_status=THUMBNAIL_STATUSES.NEEDED,
            plain_text="",
            ocr_status=None,
        )

        # Update solr
        add_items_to_solr.delay(
            [rd.pk for rd in queryset], "search.RECAPDocument"
        )

        # Do a CloudFront invalidation
        invalidate_cloudfront([f"/{path}" for path in deleted_filepaths])

        if ia_failures:
            self.message_user(
                request,
                f"Failed to remove {len(ia_failures)} item(s) from Internet "
                f"Archive. Please do so by hand. Sorry. The URL(s): "
                f"{ia_failures}.",
            )
        else:
            self.message_user(
                request,
                f"Successfully sealed and removed {queryset.count()} "
                f"document(s).",
            )


class RECAPDocumentInline(admin.StackedInline):
    model = RECAPDocument
    extra = 1

    readonly_fields = (
        "date_created",
        "date_modified",
    )
    raw_id_fields = ("tags",)

    # Essential so that we remove sealed content from Solr when updating it via
    # admin interface.
    def save_model(self, request, obj, form, change):
        obj.save(index=True)


@admin.register(DocketEntry)
class DocketEntryAdmin(CursorPaginatorAdmin):
    inlines = (RECAPDocumentInline,)
    raw_id_fields = ("docket", "tags")
    readonly_fields = (
        "date_created",
        "date_modified",
    )


class DocketEntryInline(admin.TabularInline):
    model = DocketEntry
    extra = 1
    raw_id_fields = ("tags",)


@admin.register(OriginatingCourtInformation)
class OriginatingCourtInformationAdmin(admin.ModelAdmin):
    raw_id_fields = (
        "assigned_to",
        "ordering_judge",
    )


@admin.register(Docket)
class DocketAdmin(CursorPaginatorAdmin):
    prepopulated_fields = {"slug": ["case_name"]}
    inlines = (
        DocketEntryInline,
        BankruptcyInformationInline,
        DocketAlertInline,
    )
    readonly_fields = (
        "date_created",
        "date_modified",
        "view_count",
    )
    raw_id_fields = (
        "panel",
        "tags",
        "assigned_to",
        "referred_to",
        "originating_court_information",
        "idb_data",
    )

    def save_model(
        self,
        request: HttpRequest,
        obj: Docket,
        form: ModelForm,
        change: bool,
    ) -> None:
        obj.save()
        from cl.search.tasks import add_items_to_solr

        ids = list(
            RECAPDocument.objects.filter(
                docket_entry__docket_id=obj.pk,
            ).values_list("id", flat=True)
        )
        add_items_to_solr.delay(ids, "search.RECAPDocument")

    def delete_model(self, request: HttpRequest, obj: Docket) -> None:
        # Do the query before deleting the item. Otherwise, the query returns
        # nothing.
        ids = list(
            RECAPDocument.objects.filter(
                docket_entry__docket_id=obj.pk
            ).values_list("id", flat=True)
        )

        from cl.search.tasks import delete_items

        delete_items.delay(ids, "search.RECAPDocument")
        obj.delete()


@admin.register(OpinionsCited)
class OpinionsCitedAdmin(CursorPaginatorAdmin):
    raw_id_fields = (
        "citing_opinion",
        "cited_opinion",
    )
    search_fields = ("=citing_opinion__id",)

    def save_model(self, request, obj, form, change):
        obj.save()
        from cl.search.tasks import add_items_to_solr

        add_items_to_solr.delay([obj.citing_opinion_id], "search.Opinion")


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


@admin.register(ClusterStub)
class ClusterStubAdmin(CursorPaginatorAdmin):
    list_display = (
        "id",
        "case_name",
        "case_name_full",
        "date_filed",
        "court_str",
    )
