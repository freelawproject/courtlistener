from django.contrib import admin

from cl.search.models import (
    Docket, OpinionsCited, Court, Opinion, OpinionCluster
)


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
        'author',
        'joined_by',
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
    prepopulated_fields = {"slug": ['case_name']}
    fields = (
        'docket',
        'panel',
        'non_participating_judges',
        'judges',
        'per_curiam',
        'date_filed',
        'slug',
        'citation_id',
        'case_name_short',
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
        'scdb_id',
        'scdb_decision_direction',
        'scdb_votes_majority',
        'scdb_votes_minority',
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
    )
    raw_id_fields = (
        'docket',
        'panel',
        'non_participating_judges',
    )
    list_filter = (
        'source',
    )
    readonly_fields = (
        'citation_count',
        'date_modified',
        'date_created',
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
    prepopulated_fields = {"slug": ['case_name']}
    readonly_fields = (
        'date_modified',
    )
    raw_id_fields = (
        'assigned_to',
        'referred_to',
    )


class OpinionsCitedAdmin(admin.ModelAdmin):
    raw_id_fields = (
        'citing_opinion',
        'cited_opinion',
    )
    search_fields = (
        '=citing_opinion__id',
    )

    def save_model(self, request, obj, form, change):
        obj.save()
        from cl.search.tasks import add_or_update_opinions
        add_or_update_opinions.delay([obj.citing_opinion_id],
                                     force_commit=False)

admin.site.register(Opinion, OpinionAdmin)
admin.site.register(Court, CourtAdmin)
admin.site.register(Docket, DocketAdmin)
admin.site.register(OpinionsCited, OpinionsCitedAdmin)
admin.site.register(OpinionCluster, OpinionClusterAdmin)
