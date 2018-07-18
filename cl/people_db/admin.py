from django.contrib import admin

from cl.lib.admin import CSSAdminMixin
# Judge DB imports
from cl.people_db.models import (
    ABARating, Education, Person, PoliticalAffiliation, Position,
    Race, RetentionEvent, School, Source, FinancialDisclosure,
)
# RECAP imports
from cl.people_db.models import (
    Attorney, AttorneyOrganization, AttorneyOrganizationAssociation,
    CriminalComplaint, CriminalCount, PartyType, Party, Role,
)


class RetentionEventInline(admin.TabularInline):
    model = RetentionEvent
    extra = 1


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_filter = (
        'court__jurisdiction',
    )
    inlines = (
        RetentionEventInline,
    )
    raw_id_fields = (
        'court',
        'school',
        'appointer',
        'supervisor',
        'predecessor',
    )

    def save_model(self, request, obj, form, change):
        obj.save()
        from cl.search.tasks import add_or_update_people
        add_or_update_people.delay([obj.person_id])

    def delete_model(self, request, obj):
        obj.delete()
        from cl.search.tasks import add_or_update_people
        add_or_update_people.delay([obj.person_id])


class PositionInline(admin.StackedInline):
    model = Position
    extra = 1
    fk_name = 'person'
    raw_id_fields = (
        'court',
        'school',
        'appointer',
        'supervisor',
        'predecessor',
    )


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    search_fields = (
        'id',
        'ein',
        'name',
    )


@admin.register(Education)
class EducationAdmin(admin.ModelAdmin):
    search_fields = (
        'school__name',
        'school__ein',
        'school__pk',
    )


class EducationInline(admin.TabularInline):
    model = Education
    extra = 1
    raw_id_fields = ('school',)


class PoliticalAffiliationInline(admin.TabularInline):
    model = PoliticalAffiliation
    extra = 1


class SourceInline(admin.TabularInline):
    model = Source
    extra = 1


class ABARatingInline(admin.TabularInline):
    model = ABARating
    extra = 1


@admin.register(FinancialDisclosure)
class FinancialDisclosureAdmin(admin.ModelAdmin):
    raw_id_fields = (
        'person',
    )

    def save_model(self, request, obj, form, change):
        obj.save()
        from cl.people_db.tasks import make_png_thumbnail_from_pdf
        make_png_thumbnail_from_pdf.delay(obj.pk)


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin, CSSAdminMixin):
    prepopulated_fields = {"slug": ['name_first', 'name_middle', 'name_last',
                                    'name_suffix']}
    inlines = (
        PositionInline,
        EducationInline,
        PoliticalAffiliationInline,
        SourceInline,
        ABARatingInline,
    )
    search_fields = (
        'name_last',
        'name_first',
        'fjc_id',
    )
    list_filter = (
        'gender',
    )
    list_display = (
        'name_full',
        'gender',
        'fjc_id',
    )
    raw_id_fields = (
        'is_alias_of',
    )
    readonly_fields = (
        'has_photo',
    )

    def save_model(self, request, obj, form, change):
        obj.save()
        from cl.search.tasks import add_or_update_people
        add_or_update_people.delay([obj.pk])

    def delete_model(self, request, obj):
        obj.delete()
        from cl.search.tasks import delete_items
        delete_items.delay([obj.pk], 'person')


@admin.register(Race)
class RaceAdmin(admin.ModelAdmin):
    list_display = (
        'get_race_display',
    )


@admin.register(Party)
class PartyAdmin(admin.ModelAdmin):
    search_fields = (
        'name',
    )


@admin.register(PartyType)
class PartyTypeAdmin(admin.ModelAdmin):
    raw_id_fields = (
        'party',
        'docket',
    )


@admin.register(CriminalComplaint)
class CriminalComplaintAdmin(admin.ModelAdmin):
    raw_id_fields = (
        'party_type',
    )


@admin.register(CriminalCount)
class CriminalCountAdmin(admin.ModelAdmin):
    raw_id_fields = (
        'party_type',
    )


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    raw_id_fields = (
        'party',
        'attorney',
        'docket',
    )
    list_filter = (
        'role',
    )
    list_display = (
        '__unicode__',
        'attorney',
        'get_role_display',
        'party',
    )


@admin.register(Attorney)
class AttorneyAdmin(admin.ModelAdmin):
    raw_id_fields = (
        'organizations',
    )
    search_fields = (
        'name',
    )


@admin.register(AttorneyOrganizationAssociation)
class AttorneyOrgAssAdmin(admin.ModelAdmin):
    raw_id_fields = (
        'attorney',
        'attorney_organization',
        'docket',
    )
    list_display = (
        '__unicode__',
        'attorney',
        'docket',
        'attorney_organization',
    )


@admin.register(AttorneyOrganization)
class AttorneyOrganizationAdmin(admin.ModelAdmin):
    search_fields = (
        'name',
        'address1',
        'address2',
        'city',
        'zip_code',
    )


admin.site.register(PoliticalAffiliation)
admin.site.register(RetentionEvent)
admin.site.register(Source)
admin.site.register(ABARating)
