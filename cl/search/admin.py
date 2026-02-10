from typing import Any

from admin_cursor_paginator import CursorPaginatorAdmin
from django.contrib import admin, messages
from django.db import transaction
from django.db.models import Q, QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils.html import format_html

from cl.alerts.models import DocketAlert
from cl.lib.admin import build_admin_url
from cl.lib.string_utils import trunc
from cl.search.models import (
    BankruptcyInformation,
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
    OpinionsCited,
    OriginatingCourtInformation,
    Parenthetical,
    ParentheticalGroup,
    RECAPDocument,
    ScotusDocketMetadata,
    SearchQuery,
)
from cl.search.utils import seal_documents
from cl.visualizations.models import SCOTUSMap


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
    actions = ("seal_clusters",)

    # nosemgrep: python.lang.bad-return-outside-function
    SEAL_BLOCKERS_MAP = {
        # These prevent cluster deletion
        "favorites.UserTag": lambda cluster: cluster.docket.user_tags,
        "favorites.Note": lambda cluster: cluster.docket.note_set.all().union(
            cluster.note_set.all()
        ),
        "alerts.DocketAlert": lambda cluster: cluster.docket.alerts,
        "visualizations.SCOTUSMap": lambda cluster: SCOTUSMap.objects.filter(
            Q(cluster_start=cluster)
            | Q(cluster_end=cluster)
            | Q(clusters__in=[cluster]),
            deleted=False,
        ),
        # These prevent docket deletion but not cluster deletion
        "audio.Audio": lambda cluster: cluster.docket.audio_files,
        "people_db.AttorneyOrganizationAssociation": lambda cluster: cluster.docket.attorneyorganizationassociation_set,
        "people_db.PartyType": lambda cluster: cluster.docket.party_types,
        "people_db.Role": lambda cluster: cluster.docket.role_set,
        "search.BankruptcyInformation": lambda cluster: getattr(
            cluster.docket, "bankruptcyinformation", None
        ),
        "search.Claim": lambda cluster: cluster.docket.claims,
        "search.DocketEntry": lambda cluster: cluster.docket.docket_entries,
        "search.OpinionCluster": lambda cluster: cluster.docket.clusters.exclude(
            pk=cluster.pk
        ),
    }

    # Prevent cluster deletion
    CLUSTER_BLOCKER_KEYS = [
        "favorites.UserTag",
        "favorites.Note",
        "alerts.DocketAlert",
        "visualizations.SCOTUSMap",
    ]

    # Prevent docket deletion but not cluster deletion
    DOCKET_BLOCKER_KEYS = [
        "audio.Audio",
        "people_db.AttorneyOrganizationAssociation",
        "people_db.PartyType",
        "people_db.Role",
        "search.BankruptcyInformation",
        "search.Claim",
        "search.DocketEntry",
        "search.OpinionCluster",
    ]

    def check_blocking_relations(
        self, cluster: OpinionCluster
    ) -> dict[str, bool]:
        """Check each blocker relation for the given cluster to determine
        if dependent objects exist that block deletion

        :param cluster: OpinionCluster instance to check blockers for
        :return: Dictionary mapping relation keys to boolean indicating presence of blockers
        """
        blockers_found = {}
        for key, get_relation in self.SEAL_BLOCKERS_MAP.items():
            relation = get_relation(cluster)
            if relation is None:
                blockers_found[key] = False
                continue
            if hasattr(relation, "exists"):
                blockers_found[key] = relation.exists()
            else:
                # For single related objects
                blockers_found[key] = bool(relation)
        return blockers_found

    def get_blocking_relations(
        self, cluster: OpinionCluster
    ) -> dict[str, Any]:
        """Retrieve the actual blocking related objects for a cluster, annotating
        each with an admin change-url for UI display

        :param cluster: OpinionCluster instance
        :return: Dictionary mapping relation keys to querysets or lists of blocker objects
        """

        blockers = {}
        for key, get_relation in self.SEAL_BLOCKERS_MAP.items():
            relation = get_relation(cluster)
            if relation:
                qs = relation.all() if hasattr(relation, "all") else [relation]
                for obj in qs:
                    # nosemgrep: template.xss.href-django.avoid-variable-in-href
                    obj.admin_url = reverse(
                        f"admin:{obj._meta.app_label}_{obj._meta.model_name}_change",
                        args=[obj.pk],
                    )
                blockers[key] = qs
        return blockers

    def get_urls(self):
        """Add custom admin URLs for the blocking dependencies confirmation view

        :return: List of url patterns
        """
        urls = super().get_urls()
        custom_urls = [
            path(
                "blocking-confirmation/<int:cluster_id>/",
                self.admin_site.admin_view(self.blocking_confirmation_view),
                name="opinioncluster_blocking_confirmation",
            ),
        ]
        return custom_urls + urls

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

        blocking_relations = self.get_blocking_relations(cluster)
        has_blocking = any(qs.exists() for qs in blocking_relations.values())
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

        :param request: HttpRequest triggering the action
        :param queryset: Queryset of selected OpinionCluster
        """
        error_messages = []
        sealed_count = 0

        for cluster in queryset.select_related("docket"):
            docket = cluster.docket
            blockers = self.check_blocking_relations(cluster)

            cluster_deletion_blockers = any(
                blockers.get(key, False) for key in self.CLUSTER_BLOCKER_KEYS
            )
            docket_deletion_blockers = any(
                blockers.get(key, False) for key in self.DOCKET_BLOCKER_KEYS
            )

            if cluster_deletion_blockers:
                confirm_url = reverse(
                    "admin:opinioncluster_blocking_confirmation",
                    args=[cluster.pk],
                )
                error_messages.append((cluster, confirm_url))
                continue

            with transaction.atomic():
                cluster_pk = cluster.pk
                cluster.delete()
                ClusterRedirection.objects.create(
                    reason=ClusterRedirection.SEALED,
                    deleted_cluster_id=cluster_pk,
                    cluster=None,
                )

                if not docket_deletion_blockers:
                    docket.delete()

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


@admin.register(RECAPDocument)
class RECAPDocumentAdmin(CursorPaginatorAdmin):
    search_fields = (
        "pk",
    )  # Required for search box; actual search handled by get_search_results
    search_help_text = "Search by RECAP Document ID (exact match)."
    list_select_related = ("docket_entry__docket",)  # Fix N+1 from __str__
    raw_id_fields = ("docket_entry", "tags")
    readonly_fields = (
        "date_created",
        "date_modified",
    )
    actions = ("seal_documents",)

    def get_search_results(
        self, request: HttpRequest, queryset: QuerySet, search_term: str
    ) -> tuple[QuerySet, bool]:
        """Override to search by pk without varchar casting.

        Django 6.0.1 casts non-text fields to CharField for text lookups,
        which prevents index usage on large tables. This method handles
        pk searches with direct integer comparison.

        See: https://github.com/freelawproject/courtlistener/issues/6790
        """
        if not search_term:
            return queryset, False

        try:
            pk_value = int(search_term.strip())
            return queryset.filter(pk=pk_value), False
        except ValueError:
            return queryset.none(), False

    @admin.action(description="Seal Document")
    def seal_documents(self, request: HttpRequest, queryset: QuerySet) -> None:
        ia_failures = seal_documents(queryset)
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


@admin.register(ScotusDocketMetadata)
class ScotusDocketMetadataAdmin(CursorPaginatorAdmin):
    raw_id_fields = ("docket",)
    list_display = ("__str__",)
