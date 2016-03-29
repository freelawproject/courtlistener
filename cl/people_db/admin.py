from django.contrib import admin

from cl.people_db.models import (
    Education, School, Person, Position, RetentionEvent,
    Race, PoliticalAffiliation, Source, ABARating
)


class RetentionEventInline(admin.TabularInline):
    model = RetentionEvent
    extra = 1


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


class SchoolAdmin(admin.ModelAdmin):
    search_fields = (
        'id',
        'ein',
        'name',
    )


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


class PersonAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ['name_first', 'name_middle', 'name_last',
                                    'get_name_suffix_display']}
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


class RaceAdmin(admin.ModelAdmin):
    list_display = (
        'get_race_display',
    )


admin.site.register(Person, PersonAdmin)
admin.site.register(Education, EducationAdmin)
admin.site.register(School, SchoolAdmin)
admin.site.register(Position, PositionAdmin)
admin.site.register(PoliticalAffiliation)
admin.site.register(RetentionEvent)
admin.site.register(Race, RaceAdmin)
admin.site.register(Source)
admin.site.register(ABARating)
