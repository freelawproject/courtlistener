"""Django admin configuration for people, their positions and education, parties, and attorneys."""

from admin_cursor_paginator import CursorPaginatorAdmin
from django.contrib import admin

from cl.lib.admin import AdminTweaksMixin, NotesInline

# Judge DB imports
from cl.people_db.models import (
    ABARating,
    Attorney,
    AttorneyOrganization,
    AttorneyOrganizationAssociation,
    CriminalComplaint,
    CriminalCount,
    Education,
    Party,
    PartyType,
    Person,
    PoliticalAffiliation,
    Position,
    Race,
    RetentionEvent,
    Role,
    School,
    Source,
)


class RetentionEventInline(admin.TabularInline):
    """Inline for editing a position's retention events."""

    model = RetentionEvent
    extra = 1


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    """Admin for positions, with their retention events and notes."""

    list_filter = ("court__jurisdiction",)
    inlines = (RetentionEventInline, NotesInline)
    raw_id_fields = (
        "court",
        "school",
        "appointer",
        "supervisor",
        "predecessor",
    )
    search_fields = (
        "person__name_last",
        "person__name_first",
    )


class PositionInline(admin.StackedInline):
    """Inline for editing a person's positions."""

    model = Position
    extra = 1
    fk_name = "person"
    raw_id_fields = (
        "court",
        "school",
        "appointer",
        "supervisor",
        "predecessor",
    )


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    """Admin for schools."""

    search_fields = (
        "id",
        "ein",
        "name",
    )
    inlines = (NotesInline,)
    autocomplete_fields = ("is_alias_of",)


@admin.register(Education)
class EducationAdmin(admin.ModelAdmin):
    """Admin for education records."""

    search_fields = (
        "school__name",
        "school__ein",
        "school__pk",
    )
    inlines = (NotesInline,)


class EducationInline(admin.TabularInline):
    """Inline for editing a person's education records."""

    model = Education
    extra = 1
    raw_id_fields = ("school",)


class PoliticalAffiliationInline(admin.TabularInline):
    """Inline for editing a person's political affiliations."""

    model = PoliticalAffiliation
    extra = 1


class SourceInline(admin.TabularInline):
    """Inline for editing a person's sources."""

    model = Source
    extra = 1


class ABARatingInline(admin.TabularInline):
    """Inline for editing a person's ABA ratings."""

    model = ABARating
    extra = 1


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin, AdminTweaksMixin):
    """Admin for people, with their positions, education, affiliations, sources, ratings, and notes."""

    prepopulated_fields = {
        "slug": ["name_first", "name_middle", "name_last", "name_suffix"]
    }
    inlines = (
        PositionInline,
        EducationInline,
        PoliticalAffiliationInline,
        SourceInline,
        ABARatingInline,
        NotesInline,
    )
    search_fields = (
        "name_last",
        "name_first",
        "fjc_id",
        "pk",
    )
    list_filter = ("gender",)
    list_display = (
        "name_full",
        "gender",
        "fjc_id",
    )
    raw_id_fields = ("is_alias_of",)
    readonly_fields = ("has_photo",)


@admin.register(Race)
class RaceAdmin(admin.ModelAdmin):
    """Admin for races."""

    list_display = ("get_race_display",)


@admin.register(Party)
class PartyAdmin(CursorPaginatorAdmin):
    """Admin for parties."""

    search_fields = ("name",)


@admin.register(PartyType)
class PartyTypeAdmin(CursorPaginatorAdmin):
    """Admin for party types."""

    raw_id_fields = (
        "party",
        "docket",
    )


@admin.register(CriminalComplaint)
class CriminalComplaintAdmin(admin.ModelAdmin):
    """Admin for criminal complaints."""

    raw_id_fields = ("party_type",)


@admin.register(CriminalCount)
class CriminalCountAdmin(admin.ModelAdmin):
    """Admin for criminal counts."""

    raw_id_fields = ("party_type",)


@admin.register(Role)
class RoleAdmin(CursorPaginatorAdmin):
    """Admin for attorney roles."""

    raw_id_fields = (
        "party",
        "attorney",
        "docket",
    )
    list_filter = ("role",)
    list_display = (
        "__str__",
        "attorney",
        "get_role_display",
        "party",
    )


@admin.register(Attorney)
class AttorneyAdmin(CursorPaginatorAdmin):
    """Admin for attorneys."""

    raw_id_fields = ("organizations",)
    search_fields = ("name",)


@admin.register(AttorneyOrganizationAssociation)
class AttorneyOrgAssAdmin(CursorPaginatorAdmin):
    """Admin for attorney organization associations."""

    raw_id_fields = (
        "attorney",
        "attorney_organization",
        "docket",
    )
    list_display = (
        "__str__",
        "attorney",
        "docket",
        "attorney_organization",
    )


@admin.register(AttorneyOrganization)
class AttorneyOrganizationAdmin(CursorPaginatorAdmin):
    """Admin for attorney organizations."""

    search_fields = (
        "name",
        "address1",
        "address2",
        "city",
        "zip_code",
    )


admin.site.register(PoliticalAffiliation)
admin.site.register(RetentionEvent)
admin.site.register(Source)
admin.site.register(ABARating)
