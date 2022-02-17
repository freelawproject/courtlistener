from django.contrib import admin
from django.forms import ModelForm
from django.http import HttpRequest

from cl.alerts.admin import DocketAlertInline
from cl.search.models import (
    BankruptcyInformation,
    Citation,
    Claim,
    ClaimHistory,
    Court,
    Docket,
    DocketEntry,
    Opinion,
    OpinionCluster,
    OpinionsCited,
    OriginatingCourtInformation,
    Parenthetical,
    RECAPDocument,
)


@admin.register(Opinion)
class OpinionAdmin(admin.ModelAdmin):
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
class CitationAdmin(admin.ModelAdmin):
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
class OpinionClusterAdmin(admin.ModelAdmin):
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


class ClaimHistoryInline(admin.StackedInline):
    model = ClaimHistory
    extra = 1


@admin.register(Claim)
class ClaimAdmin(admin.ModelAdmin):
    raw_id_fields = ("docket", "tags")

    inlines = (ClaimHistoryInline,)


class BankruptcyInformationInline(admin.StackedInline):
    model = BankruptcyInformation


@admin.register(BankruptcyInformation)
class BankruptcyInformationAdmin(admin.ModelAdmin):
    raw_id_fields = ("docket",)


@admin.register(RECAPDocument)
class RECAPDocumentAdmin(admin.ModelAdmin):
    raw_id_fields = ("docket_entry", "tags")

    readonly_fields = (
        "date_created",
        "date_modified",
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
class DocketEntryAdmin(admin.ModelAdmin):
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
class DocketAdmin(admin.ModelAdmin):
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
class OpinionsCitedAdmin(admin.ModelAdmin):
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
class ParentheticalAdmin(admin.ModelAdmin):
    raw_id_fields = (
        "describing_opinion",
        "described_opinion",
    )
    search_fields = ("=describing_opinion_id",)
