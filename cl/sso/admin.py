import csv

from django.contrib import admin, messages
from django.db.models import Count, Q, QuerySet
from django.http import HttpRequest, HttpResponse
from django.utils.html import format_html_join
from django.utils.safestring import mark_safe

from cl.sso.models import (
    AuthEvent,
    Organization,
    OrganizationDomain,
    OrganizationMembership,
    SSOConnection,
    SSOEmailException,
)
from cl.sso.throttles import sync_organization_throttles


class OrganizationDomainInline(admin.TabularInline):
    """An organization's email domains."""

    model = OrganizationDomain
    extra = 0
    fields = ("domain", "enforcement", "verified_at")


class SSOConnectionInline(admin.TabularInline):
    """An organization's IdP connections, with the URLs its IdP needs."""

    model = SSOConnection
    extra = 0
    raw_id_fields = ("social_app",)
    fields = ("social_app", "is_enabled", "idp_settings")
    readonly_fields = ("idp_settings",)

    @admin.display(description="URLs for the IdP")
    def idp_settings(self, obj: SSOConnection) -> str:
        """Show the URLs to send the organization's IdP admin."""
        if not obj.pk:
            return "Save first."
        return format_html_join(
            mark_safe("<br>"),
            "{}: <code>{}</code>",
            obj.get_idp_settings().items(),
        )


class OrganizationMembershipInline(admin.TabularInline):
    """The people who belong to an organization."""

    model = OrganizationMembership
    extra = 0
    raw_id_fields = ("user",)
    readonly_fields = ("last_sso_login",)


class SSOEmailExceptionInline(admin.TabularInline):
    """Addresses exempt from an organization's enforcement."""

    model = SSOEmailException
    extra = 0


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    """Organizations, with their domains, connections and members."""

    list_display = (
        "name",
        "membership_level",
        "seats",
        "termination_date",
        "is_staff_organization",
    )
    list_filter = ("is_staff_organization", "membership_level")
    search_fields = ("name", "slug", "domains__domain")
    prepopulated_fields = {"slug": ("name",)}
    inlines = (
        OrganizationDomainInline,
        SSOConnectionInline,
        OrganizationMembershipInline,
        SSOEmailExceptionInline,
    )
    actions = ("export_members", "sync_throttles")

    def get_queryset(self, request: HttpRequest) -> QuerySet[Organization]:
        """Annotate seat counts so the list page doesn't query per row."""
        return (
            super()
            .get_queryset(request)
            .annotate(
                seat_count=Count(
                    "memberships", filter=Q(memberships__has_seat=True)
                )
            )
        )

    @admin.display(description="Seats used")
    def seats(self, obj: Organization) -> str:
        """Show seats used against the limit, e.g. "12 / 25"."""
        limit = "∞" if obj.seat_limit is None else obj.seat_limit
        return f"{obj.seat_count} / {limit}"  # type: ignore[attr-defined]

    def save_related(self, request, form, formsets, change) -> None:
        """Re-sync members' API throttles after the organization changes.

        The organization's level decides its members' API rates, so a
        level change in the admin has to reach them.
        """
        super().save_related(request, form, formsets, change)
        sync_organization_throttles(form.instance)

    @admin.action(description="Export members as CSV")
    def export_members(
        self, request: HttpRequest, queryset: QuerySet[Organization]
    ) -> HttpResponse:
        """Download one row per member of the selected organizations."""
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            'attachment; filename="organization-members.csv"'
        )
        writer = csv.writer(response)
        writer.writerow(
            [
                "organization",
                "username",
                "email",
                "role",
                "source",
                "has_seat",
                "last_sso_login",
            ]
        )
        memberships = OrganizationMembership.objects.filter(
            organization__in=queryset
        ).select_related("organization", "user")
        for m in memberships:
            writer.writerow(
                [
                    m.organization.slug,
                    m.user.username,
                    m.user.email,
                    m.role,
                    m.source,
                    m.has_seat,
                    m.last_sso_login.isoformat() if m.last_sso_login else "",
                ]
            )
        return response

    @admin.action(description="Re-sync members' API throttles")
    def sync_throttles(
        self, request: HttpRequest, queryset: QuerySet[Organization]
    ) -> None:
        """Bring members' API rates in line with their organization's level."""
        for organization in queryset:
            sync_organization_throttles(organization)
        self.message_user(request, "Throttles synced.", messages.SUCCESS)


@admin.register(AuthEvent)
class AuthEventAdmin(admin.ModelAdmin):
    """A read-only view of the sign-in audit log."""

    list_display = (
        "date_created",
        "user",
        "method",
        "outcome",
        "connection",
        "ip_address",
        "detail",
    )
    list_filter = ("method", "outcome")
    search_fields = ("user__username", "user__email", "ip_address")
    raw_id_fields = ("user", "connection")
    date_hierarchy = "date_created"

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Audit records are only ever written by the application."""
        return False

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        """Audit records can't be edited."""
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        """Audit records can't be deleted from the admin."""
        return False
