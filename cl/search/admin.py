from typing import Any

from admin_cursor_paginator import CursorPaginatorAdmin
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils.html import format_html

from cl.alerts.models import DocketAlert
from cl.lib.admin import (
    AdminLinkConfig,
    IndexedPkSearchMixin,
    SealableDocumentAdmin,
    generate_admin_links,
)
from cl.lib.string_utils import trunc
from cl.search.deletion_utils import (
    get_blocking_relations,
    get_deletion_blockers,
    seal_cluster,
)
from cl.search.models import (
    BankruptcyInformation,
    CaseTransfer,
    Citation,
    Claim,
    ClaimHistory,
    ClusterRedirection,
    Court,
    Courthouse,
    Docket,
    DocketEntry,
    Opinion,
    OpinionCluster,
    OpinionContent,
    OpinionsCited,
    OriginatingCourtInformation,
    Parenthetical,
    ParentheticalGroup,
    RECAPDocument,
    SCOTUSDocketEntry,
    ScotusDocketMetadata,
    SCOTUSDocument,
    SearchQuery,
    TrialCourtData,
)
from cl.search.state.florida.models import (
    FloridaDocketEntry,
    FloridaDocument,
)
from cl.search.state.new_york.models import (
    NYCoADocketEntry,
    NYCoADocketIssue,
    NYCoADocketMetadata,
    NYCoADocument,
)
from cl.search.state.texas.models import TexasDocketEntry, TexasDocument


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
        "main_version",
        "date_created",
        "date_modified",
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("cluster")


@admin.register(OpinionContent)
class OpinionContentAdmin(CursorPaginatorAdmin):
    raw_id_fields = ("opinion",)
    search_fields = ("content",)
    readonly_fields = (
        "date_created",
        "date_modified",
    )
    list_filter = ("source",)
    list_display = ("__str__", "source", "extraction_type")


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
class OpinionClusterAdmin(IndexedPkSearchMixin, CursorPaginatorAdmin):
    change_form_template = "admin/change_form_with_custom_links.html"
    prepopulated_fields = {"slug": ["case_name"]}
    inlines = (CitationInline,)
    raw_id_fields = (
        "docket",
        "panel",
        "non_participating_judges",
    )
    list_filter = ("blocked",)
    search_fields = (
        "pk",
    )  # Required for search box; actual search handled by IndexedPkSearchMixin
    search_help_text = "Search by OpinionCluster ID (exact match)."
    readonly_fields = (
        "citation_count",
        "date_modified",
        "date_created",
    )
    actions = ("seal_clusters",)

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: dict[str, Any] | None = None,
    ) -> HttpResponse:
        """Add a "Seal Cluster" button to the change form

        :param request: HttpRequest object
        :param object_id: PK of the OpinionCluster being edited
        :param form_url: URL the change form posts to
        :param extra_context: Additional template context
        :return: The rendered change form
        """
        extra_context = extra_context or {}
        extra_context["custom_links"] = [
            {
                "href": reverse(
                    "admin:opinioncluster_seal_confirmation",
                    args=[object_id],
                ),
                "label": "Seal Cluster",
            }
        ]
        return super().change_view(
            request, object_id, form_url, extra_context=extra_context
        )

    def get_urls(self):
        """Add custom admin URLs for sealing and blocking-dependency views

        :return: List of url patterns
        """
        urls = super().get_urls()
        custom_urls = [
            path(
                "blocking-confirmation/<int:cluster_id>/",
                self.admin_site.admin_view(self.blocking_confirmation_view),
                name="opinioncluster_blocking_confirmation",
            ),
            path(
                "seal-cluster/<int:cluster_id>/",
                self.admin_site.admin_view(self.seal_cluster_view),
                name="opinioncluster_seal_confirmation",
            ),
        ]
        return custom_urls + urls

    def seal_cluster_view(
        self, request: HttpRequest, cluster_id: int
    ) -> HttpResponse:
        """Confirmation page (GET) and execution (POST) for sealing one cluster

        This is the single-object counterpart to the `seal_clusters` action,
        reachable from the "Seal Cluster" button on the change form. Both go
        through `deletion_utils.get_deletion_blockers` and
        `deletion_utils.seal_cluster`, so the two paths can't drift.

        On GET, a cluster with dependencies that block deletion redirects to
        the blocking-confirmation page so the admin can see what needs to be
        resolved first. Otherwise we render a confirmation form that says
        whether the associated docket will be removed along with the cluster.

        :param request: HttpRequest object
        :param cluster_id: ID of the OpinionCluster to seal
        :return: Redirect or rendered confirmation page
        """
        cluster = get_object_or_404(OpinionCluster, pk=cluster_id)
        # `admin_view` only checks that the user is active staff, so gate the
        # deletion on the model permission the way Django's delete_view does.
        if not self.has_delete_permission(request, cluster):
            raise PermissionDenied

        cluster_blocked, docket_blocked = get_deletion_blockers(cluster)
        if cluster_blocked:
            return HttpResponseRedirect(
                reverse(
                    "admin:opinioncluster_blocking_confirmation",
                    args=[cluster_id],
                )
            )

        if request.method == "POST":
            seal_cluster(cluster, delete_docket=not docket_blocked)
            self.message_user(
                request,
                f"Sealed cluster {cluster_id}.",
                messages.SUCCESS,
            )
            return HttpResponseRedirect(
                reverse("admin:search_opinioncluster_changelist")
            )

        context = {
            **self.admin_site.each_context(request),
            "title": f"Seal OpinionCluster #{cluster_id}?",
            "cluster": cluster,
            "docket_will_be_deleted": not docket_blocked,
        }
        return render(request, "admin/seal_cluster_confirmation.html", context)

    def blocking_confirmation_view(
        self, request: HttpRequest, cluster_id: int
    ) -> HttpResponse:
        """View that shows confirmation and details of blocking dependencies
        preventing sealing of a cluster

        :param request: HttpRequest object
        :param cluster_id: ID of the OpinionCluster being checked
        :return: HttpResponse rendering template with blocking relations
        """
        cluster = get_object_or_404(OpinionCluster, pk=cluster_id)

        blocking_relations = get_blocking_relations(cluster)
        # A one-to-one blocker comes back as a plain list, so ask about
        # truthiness rather than calling `exists()`, which only querysets have.
        has_blocking = any(blocking_relations.values())
        context = {
            **self.admin_site.each_context(request),
            "title": "Blocking dependencies preventing cluster sealing",
            "cluster": cluster,
            "blocking_relations": blocking_relations,
            "has_blocking": has_blocking,
        }
        return render(
            request, "admin/seal_cluster_blocking_confirmation.html", context
        )

    @admin.action(description="Seal selected opinion clusters")
    def seal_clusters(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Custom admin action to seal (delete) selected clusters after ensuring
        no blocking dependencies exist. Creates a ClusterRedirection record
        for each sealed cluster

        This is the bulk counterpart to `seal_cluster_view`; both share
        `deletion_utils.get_deletion_blockers` and `deletion_utils.seal_cluster`.

        :param request: HttpRequest triggering the action
        :param queryset: Queryset of selected OpinionCluster
        """
        # The changelist only requires view or change permission, so gate the
        # deletion the way Django's own delete_selected action does. Checked
        # once up front rather than per cluster, so a failure can't leave a
        # partially sealed queryset behind.
        if not self.has_delete_permission(request):
            raise PermissionDenied

        error_messages = []
        sealed_count = 0

        for cluster in queryset.select_related("docket"):
            cluster_blocked, docket_blocked = get_deletion_blockers(cluster)
            if cluster_blocked:
                confirm_url = reverse(
                    "admin:opinioncluster_blocking_confirmation",
                    args=[cluster.pk],
                )
                error_messages.append((cluster, confirm_url))
                continue

            seal_cluster(cluster, delete_docket=not docket_blocked)
            sealed_count += 1

        if sealed_count:
            self.message_user(
                request, f"Sealed {sealed_count} cluster(s).", messages.SUCCESS
            )

        if error_messages:
            for cluster, url in error_messages:
                message = format_html(
                    "ERROR: Problem sealing cluster id: {}{}",
                    cluster.pk,
                    format_html(
                        ' - <a href="{}" target="_blank">View Dependencies</a>',
                        url,
                    )
                    if url
                    else "",
                )
                self.message_user(request, message, messages.WARNING)


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


@admin.register(CaseTransfer)
class CaseTransferAdmin(CursorPaginatorAdmin):
    raw_id_fields = (
        "origin_court",
        "origin_docket",
        "destination_court",
        "destination_docket",
    )
    list_display = (
        "pk",
        "origin_court",
        "origin_docket_number",
        "destination_court",
        "destination_docket_number",
        "transfer_date",
        "transfer_type",
    )
    list_filter = (
        "transfer_type",
        "transfer_date",
    )
    search_fields = (
        "origin_docket_number",
        "destination_docket_number",
    )
    readonly_fields = (
        "date_created",
        "date_modified",
    )


@admin.register(RECAPDocument)
class RECAPDocumentAdmin(
    IndexedPkSearchMixin, SealableDocumentAdmin, CursorPaginatorAdmin
):
    change_form_template = "admin/change_form_with_custom_links.html"
    search_fields = (
        "pk",
    )  # Required for search box; actual search handled by IndexedPkSearchMixin
    search_help_text = "Search by RECAP Document ID (exact match)."
    list_select_related = ("docket_entry__docket",)  # Fix N+1 from __str__
    raw_id_fields = ("docket_entry", "tags")
    readonly_fields = (
        "date_created",
        "date_modified",
    )
    actions = ("seal_documents",)

    # SealableDocumentAdmin config
    seal_url_name = "recapdocument_seal_confirmation"
    seal_link_label = "Seal Document"
    seal_heading_template = "Seal RECAP Document #{pk}?"
    seal_model = RECAPDocument
    seal_change_url_name = "admin:search_recapdocument_change"

    def get_seal_documents(self, obj):
        return [obj]

    @admin.action(description="Seal Document")
    def seal_documents(self, request: HttpRequest, queryset: QuerySet) -> None:
        self._seal_and_report(request, queryset=queryset)


class RECAPDocumentInline(admin.StackedInline):
    model = RECAPDocument
    extra = 1

    readonly_fields = (
        "date_created",
        "date_modified",
    )
    raw_id_fields = ("tags",)


@admin.register(DocketEntry)
class DocketEntryAdmin(SealableDocumentAdmin, CursorPaginatorAdmin):
    change_form_template = "admin/change_form_with_custom_links.html"
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
    actions = ("seal_docket_entry_documents",)

    # SealableDocumentAdmin config
    seal_url_name = "docketentry_seal_confirmation"
    seal_link_label = "Seal Documents"
    seal_heading_template = "Seal documents in Docket Entry #{pk}?"
    seal_model = DocketEntry
    seal_change_url_name = "admin:search_docketentry_change"

    def get_seal_documents(self, obj):
        return list(
            obj.recap_documents.all().order_by(
                "document_number", "attachment_number"
            )
        )

    @admin.action(description="Seal documents for selected docket entries")
    def seal_docket_entry_documents(
        self, request: HttpRequest, queryset: QuerySet
    ) -> None:
        docs = RECAPDocument.objects.filter(docket_entry__in=queryset)
        self._seal_and_report(request, queryset=docs)

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
    change_form_template = "admin/change_form_with_custom_links.html"
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
        custom_links: list[AdminLinkConfig] = [
            {
                "label": "View Docket Entries",
                "model_class": DocketEntry,
                "query_params": {"docket": object_id},
            },
            {
                "label": "View Docket Alerts",
                "model_class": DocketAlert,
                "query_params": {"docket": object_id},
            },
        ]
        extra_context["custom_links"] = generate_admin_links(custom_links)
        return super().change_view(
            request, object_id, form_url, extra_context=extra_context
        )


@admin.register(TrialCourtData)
class TrialCourtDataAdmin(CursorPaginatorAdmin):
    raw_id_fields = (
        "docket",
        "judge",
    )
    autocomplete_fields = ("court",)
    readonly_fields = (
        "date_created",
        "date_modified",
    )
    list_display = (
        "__str__",
        "docket_number_trial",
        "court_name",
        "date_filed",
    )
    search_help_text = "Search by docket ID or trial court docket number."
    search_fields = (
        "=docket__id",
        "docket_number_trial",
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
    list_display = ("__str__", "engine", "source", "query_mode")
    list_filter = ("engine", "source", "query_mode")
    search_fields = ("user__username",)


@admin.register(ClusterRedirection)
class ClusterRedirectionAdmin(admin.ModelAdmin):
    raw_id_fields = ("cluster",)
    list_display = (
        "pk",
        "deleted_cluster_id",
        "cluster",
    )
    list_filter = ("reason",)

    def has_delete_permission(
        self, request: HttpRequest, obj: ClusterRedirection | None = None
    ) -> bool:
        """Prevent deletion of cluster redirections via the admin.

        :param request: The HTTP request.
        :param obj: The object being deleted, if any.
        :returns: Always False.
        """
        return False


@admin.register(ScotusDocketMetadata)
class ScotusDocketMetadataAdmin(CursorPaginatorAdmin):
    raw_id_fields = ("docket",)
    list_display = ("__str__",)


class SCOTUSDocumentInline(admin.StackedInline):
    model = SCOTUSDocument
    extra = 1

    readonly_fields = (
        "date_created",
        "date_modified",
    )


@admin.register(SCOTUSDocketEntry)
class SCOTUSDocketEntryAdmin(CursorPaginatorAdmin):
    inlines = (SCOTUSDocumentInline,)
    search_help_text = (
        "Search SCOTUSDocketEntries by Docket ID or sequence number."
    )
    search_fields = (
        "docket__id",
        "sequence_number",
    )
    list_display = (
        "get_pk",
        "get_trunc_description",
        "date_filed",
        "entry_number",
        "sequence_number",
    )
    raw_id_fields = ("docket",)
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


@admin.register(SCOTUSDocument)
class SCOTUSDocumentAdmin(IndexedPkSearchMixin, CursorPaginatorAdmin):
    search_fields = (
        "pk",
    )  # Required for search box; actual search handled by IndexedPkSearchMixin
    search_help_text = "Search by SCOTUSDocument Document ID (exact match)."
    list_select_related = ("docket_entry__docket",)  # Fix N+1 from __str__
    raw_id_fields = ("docket_entry",)
    readonly_fields = (
        "date_created",
        "date_modified",
    )


class TexasDocumentInline(admin.StackedInline):
    model = TexasDocument
    extra = 1

    readonly_fields = (
        "date_created",
        "date_modified",
    )


@admin.register(TexasDocument)
class TexasDocumentAdmin(CursorPaginatorAdmin):
    search_fields = ("media_version_id",)
    search_help_text = (
        "Search by Texas Document media version ID (exact match)."
    )
    list_select_related = ("docket_entry__docket",)  # Fix N+1 from __str__
    raw_id_fields = ("docket_entry",)
    readonly_fields = (
        "date_created",
        "date_modified",
    )


@admin.register(TexasDocketEntry)
class TexasDocketEntryAdmin(CursorPaginatorAdmin):
    inlines = (TexasDocumentInline,)
    search_help_text = (
        "Search TexasDocketEntries by Docket ID or sequence number."
    )
    search_fields = (
        "docket__id",
        "sequence_number",
    )
    list_display = (
        "get_pk",
        "appellate_brief",
        "get_trunc_description",
        "get_trunc_remarks",
        "disposition",
        "date_filed",
        "entry_type",
        "sequence_number",
    )
    raw_id_fields = ("docket",)
    readonly_fields = (
        "date_created",
        "date_modified",
    )
    list_filter = ("date_filed", "date_created", "date_modified")

    @admin.display(description="Texas docket entry")
    def get_pk(self, obj):
        return obj.pk

    @admin.display(description="Description")
    def get_trunc_description(self, obj):
        return trunc(obj.description, 35, ellipsis="...")

    @admin.display(description="Remarks")
    def get_trunc_remarks(self, obj):
        return trunc(obj.remarks, 35, ellipsis="...")


class FloridaDocumentInline(admin.StackedInline):
    model = FloridaDocument
    extra = 1

    readonly_fields = (
        "date_created",
        "date_modified",
    )


@admin.register(FloridaDocument)
class FloridaDocumentAdmin(CursorPaginatorAdmin):
    search_fields = ("link_uuid",)
    search_help_text = "Search by Florida Document link UUID (exact match)."
    list_select_related = ("docket_entry__docket",)  # Fix N+1 from __str__
    raw_id_fields = ("docket_entry",)
    readonly_fields = (
        "date_created",
        "date_modified",
    )


@admin.register(FloridaDocketEntry)
class FloridaDocketEntryAdmin(CursorPaginatorAdmin):
    inlines = (FloridaDocumentInline,)
    search_help_text = (
        "Search FloridaDocketEntries by Docket ID or docket entry UUID."
    )
    search_fields = (
        "docket__id",
        "docket_entry_uuid",
    )
    list_display = (
        "get_pk",
        "entry_name",
        "get_trunc_description",
        "status",
        "date_filed",
        "entry_type",
        "docket_entry_uuid",
    )
    raw_id_fields = (
        "docket",
        "submitted_by",
    )
    readonly_fields = (
        "date_created",
        "date_modified",
    )
    list_filter = ("date_filed", "date_created", "date_modified")

    @admin.display(description="Florida docket entry")
    def get_pk(self, obj):
        return obj.pk

    @admin.display(description="Description")
    def get_trunc_description(self, obj):
        return trunc(obj.description or "", 35, ellipsis="...")


class NYCoADocketIssueInline(admin.StackedInline):
    model = NYCoADocketIssue
    extra = 1

    readonly_fields = (
        "date_created",
        "date_modified",
    )


@admin.register(NYCoADocketMetadata)
class NYCoADocketMetadataAdmin(CursorPaginatorAdmin):
    inlines = (NYCoADocketIssueInline,)
    raw_id_fields = ("docket",)
    list_display = ("__str__",)
    readonly_fields = (
        "date_created",
        "date_modified",
    )


class NYCoADocumentInline(admin.StackedInline):
    model = NYCoADocument
    extra = 1

    readonly_fields = (
        "date_created",
        "date_modified",
    )


@admin.register(NYCoADocument)
class NYCoADocumentAdmin(CursorPaginatorAdmin):
    search_fields = ("file_name",)
    search_help_text = "Search by NYCoA Document file name."
    list_select_related = ("docket_entry__docket",)  # Fix N+1 from __str__
    list_display = (
        "get_pk",
        "file_name",
        "doc_type",
        "available",
    )
    raw_id_fields = ("docket_entry",)
    readonly_fields = (
        "date_created",
        "date_modified",
    )

    @admin.display(description="NYCoA document")
    def get_pk(self, obj):
        return obj.pk


@admin.register(NYCoADocketEntry)
class NYCoADocketEntryAdmin(CursorPaginatorAdmin):
    inlines = (NYCoADocumentInline,)
    search_help_text = (
        "Search NYCoADocketEntries by Docket ID or Court-PASS entry ID."
    )
    search_fields = (
        "docket__id",
        "docket_entry_id",
    )
    list_display = (
        "get_pk",
        "filing_type",
        "filing_role",
        "filing_doctype",
        "date_filed",
        "docket_entry_id",
    )
    raw_id_fields = (
        "docket",
        "party",
    )
    readonly_fields = (
        "date_created",
        "date_modified",
    )
    list_filter = ("date_filed", "date_created", "date_modified")

    @admin.display(description="NYCoA docket entry")
    def get_pk(self, obj):
        return obj.pk
