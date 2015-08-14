from cl.search.models import (
    Docket, OpinionsCited, Court, Opinion, OpinionCluster
)

from django.contrib import admin

class OpinionAdmin(admin.ModelAdmin):
    fields = (
        'cluster',
        'author',
        'joined_by',
        'type',
        'sha1',
        'download_url',
        'local_path',
        'extracted_by_ocr',
        'plain_text',
        'html',
        'html_lawbox',
        'html_columbia',
        'html_with_citations',
        'date_created',
        'date_modified',
    )
    raw_id_fields = (
        'cluster',
    )
    search_fields = (
        'plain_text',
        'html',
        'html_lawbox',
        'html_columbia',
    )
    readonly_fields = (
        'date_created',
        'date_modified',
    )


class OpinionClusterAdmin(admin.ModelAdmin):
    fields = (
        'docket',
        'panel',
        'non_participating_judges',
        'judges',
        'per_curiam',
        'date_filed',
        'slug',
        'citation_id',
        'case_name',
        'case_name_full',
        'federal_cite_one',
        'federal_cite_two',
        'federal_cite_three',
        'state_cite_one',
        'state_cite_two',
        'state_cite_three',
        'state_cite_regional',
        'specialty_cite_one',
        'scotus_early_cite',
        'lexis_cite',
        'westlaw_cite',
        'neutral_cite',
        'supreme_court_db_id',
        'source',
        'procedural_history',
        'attorneys',
        'nature_of_suit',
        'posture',
        'syllabus',
        'citation_count',
        'precedential_status',
        'blocked',
        'date_blocked',
        'date_modified',
    )
    raw_id_fields = (
        'docket',
    )
    list_filter = (
        'source',
    )
    readonly_fields = (
        'date_modified',
        'citation_count',
    )


class CourtAdmin(admin.ModelAdmin):
    list_display = (
        'full_name',
        'short_name',
        'position',
        'in_use',
        'pk'
    )
    list_filter = (
        'jurisdiction',
        'in_use',
    )
    search_fields = (
        'full_name',
        'short_name',
        'id',
    )

class DocketAdmin(admin.ModelAdmin):
    readonly_fields = (
        'date_modified',
    )

admin.site.register(Opinion, OpinionAdmin)
admin.site.register(Court, CourtAdmin)
admin.site.register(Docket, DocketAdmin)
admin.site.register(OpinionsCited, admin.ModelAdmin)
admin.site.register(OpinionCluster, OpinionClusterAdmin)
