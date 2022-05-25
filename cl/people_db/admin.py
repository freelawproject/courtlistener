from admin_cursor_paginator import CursorPaginatorAdmin
from django.contrib import admin
from django.db.models import QuerySet
from django.forms import ModelForm
from django.http import HttpRequest

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
from cl.search.tasks import add_items_to_solr, delete_items


class RetentionEventInline(admin.TabularInline):
    model = RetentionEvent
    extra = 1


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
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

    def save_model(
        self,
        request: HttpRequest,
        obj: Position,
        form: ModelForm,
        change: bool,
    ) -> None:
        obj.save()
        from cl.search.tasks import add_items_to_solr

        add_items_to_solr.delay([obj.person_id], "people_db.Person")

    def delete_model(self, request: HttpRequest, obj: Position) -> None:
        # Update the person to remove the position from them.
        obj.delete()
        from cl.search.tasks import add_items_to_solr

        add_items_to_solr.delay([obj.person_id], "people_db.Person")


class PositionInline(admin.StackedInline):
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
    search_fields = (
        "id",
        "ein",
        "name",
    )
    inlines = (NotesInline,)


@admin.register(Education)
class EducationAdmin(admin.ModelAdmin):
    search_fields = (
        "school__name",
        "school__ein",
        "school__pk",
    )
    inlines = (NotesInline,)


class EducationInline(admin.TabularInline):
    model = Education
    extra = 1
    raw_id_fields = ("school",)


class PoliticalAffiliationInline(admin.TabularInline):
    model = PoliticalAffiliation
    extra = 1


class SourceInline(admin.TabularInline):
    model = Source
    extra = 1


class ABARatingInline(admin.TabularInline):
    model = ABARating
    extra = 1


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin, AdminTweaksMixin):
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
    actions = ("update_in_solr", "delete_from_solr")

    def save_model(self, request, obj, form, change):
        obj.save()
        from cl.search.tasks import add_items_to_solr

        add_items_to_solr.delay([obj.pk], "people_db.Person")

    def delete_model(self, request, obj):
        obj.delete()
        from cl.search.tasks import delete_items

        delete_items.delay([obj.pk], "people_db.Person")

    @admin.action(description="Update selected people in Solr")
    def update_in_solr(self, request: HttpRequest, queryset: QuerySet) -> None:
        add_items_to_solr.delay([p.pk for p in queryset], "people_db.Person")
        self.message_user(
            request,
            f"Successfully updated {queryset.count()} people in Solr",
        )

    @admin.action(description="Delete selected people from Solr")
    def delete_from_solr(
        self, request: HttpRequest, queryset: QuerySet
    ) -> None:
        delete_items.delay([p.pk for p in queryset], "people_db.Person")
        self.message_user(
            request,
            f"Successfully deleted {queryset.count()} people from Solr",
        )


@admin.register(Race)
class RaceAdmin(admin.ModelAdmin):
    list_display = ("get_race_display",)


@admin.register(Party)
class PartyAdmin(CursorPaginatorAdmin):
    search_fields = ("name",)


@admin.register(PartyType)
class PartyTypeAdmin(CursorPaginatorAdmin):
    raw_id_fields = (
        "party",
        "docket",
    )


@admin.register(CriminalComplaint)
class CriminalComplaintAdmin(admin.ModelAdmin):
    raw_id_fields = ("party_type",)


@admin.register(CriminalCount)
class CriminalCountAdmin(admin.ModelAdmin):
    raw_id_fields = ("party_type",)


@admin.register(Role)
class RoleAdmin(CursorPaginatorAdmin):
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
    raw_id_fields = ("organizations",)
    search_fields = ("name",)


@admin.register(AttorneyOrganizationAssociation)
class AttorneyOrgAssAdmin(CursorPaginatorAdmin):
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
