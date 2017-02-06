from django.conf import settings
from django.contrib import admin

from cl.people_db.models import (
    Education, School, Person, Position, RetentionEvent, Race,
    PoliticalAffiliation, Source, ABARating, PartyType,
    Party, Role, Attorney, AttorneyOrganization
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


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
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
        delete_items.delay([obj.pk], settings.SOLR_PEOPLE_URL)


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
    raw_id_fields = ('party',)


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
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
