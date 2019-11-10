from django.contrib import admin

from cl.recap.models import ProcessingQueue, FjcIntegratedDatabase, \
    PacerFetchQueue


@admin.register(ProcessingQueue)
class ProcessingQueueAdmin(admin.ModelAdmin):
    list_display = (
        '__str__',
        'court',
        'pacer_case_id',
        'document_number',
        'attachment_number',
    )
    list_filter = (
        'status',
    )
    search_fields = (
        'pacer_case_id',
        'court__pk',
    )
    readonly_fields = (
        'date_modified',
        'date_created',
    )
    raw_id_fields = (
        'uploader',
        'docket',
        'docket_entry',
        'recap_document',
    )


@admin.register(PacerFetchQueue)
class PacerFetchQueueAdmin(admin.ModelAdmin):
    list_display = (
        '__str__',
        'court',
        'request_type',
    )
    list_filter = (
        'status',
        'request_type',
    )
    readonly_fields = (
        'date_created',
        'date_modified',
    )
    raw_id_fields = (
        'user',
        'docket',
        'recap_document',
    )


admin.site.register(FjcIntegratedDatabase)
