from django.contrib import admin

from cl.recap.models import ProcessingQueue, FjcIntegratedDatabase


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


admin.site.register(FjcIntegratedDatabase)
