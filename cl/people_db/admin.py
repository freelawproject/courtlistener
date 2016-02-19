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


class PositionInline(admin.StackedInline):
    model = Position
    extra = 1
    fk_name = 'judge'
    raw_id_fields = ('court',)


class EducationAdmin(admin.ModelAdmin):
    search_fields = (
        'school__name',
        'school__ein',
    )


class EducationInline(admin.TabularInline):
    model = Education
    extra = 1
    raw_id_fields = ('school',)

class PoliticalAffiliationJudgeInline(admin.TabularInline):
    """Affiliations can be tied to judges or politicians.

    This class is to be inlined with judges.
    """
    model = PoliticalAffiliation
    extra = 1
    exclude = (
        'politician',
    )


class PoliticalAffiliationPoliticianInline(admin.TabularInline):
    """Affiliations can be tied to judges or politicians.

    This class is to be inlined with politicians.
    """
    model = PoliticalAffiliation
    extra = 1
    exclude = (
        'judge',
    )


class PoliticianAdmin(admin.ModelAdmin):
    inlines = (
        PoliticalAffiliationPoliticianInline,
    )
    list_filter = (
        'office',
    )
    search_fields = (
        'name_last',
        'name_first',
    )


class SourceInline(admin.TabularInline):
    model = Source
    extra = 1


class ABARatingInline(admin.TabularInline):
    model = ABARating
    extra = 1


class PersonAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ['name_first', 'name_middle', 'name_last',
                                    'name_suffix']}
    inlines = (
        PositionInline,
        EducationInline,
        PoliticalAffiliationJudgeInline,
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


admin.site.register(Person, PersonAdmin)
admin.site.register(Education, EducationAdmin)
admin.site.register(School)
admin.site.register(Position, PositionAdmin)
admin.site.register(PoliticalAffiliation)
admin.site.register(RetentionEvent)
admin.site.register(Race)
admin.site.register(Source)
admin.site.register(ABARating)
