from admin_cursor_paginator import CursorPaginatorAdmin
from django.contrib import admin

from cl.recap.models import (
    FjcIntegratedDatabase,
    PacerFetchQueue,
    PacerHtmlFiles,
    ProcessingQueue,
)


@admin.register(ProcessingQueue)
class ProcessingQueueAdmin(CursorPaginatorAdmin):
    list_display = (
        "__str__",
        "court",
        "pacer_case_id",
        "document_number",
        "attachment_number",
    )
    list_filter = ("status",)
    search_fields = (
        "pacer_case_id",
        "court__pk",
    )
    readonly_fields = (
        "date_modified",
        "date_created",
    )
    raw_id_fields = (
        "uploader",
        "docket",
        "docket_entry",
        "recap_document",
    )


@admin.register(PacerFetchQueue)
class PacerFetchQueueAdmin(CursorPaginatorAdmin):
    list_display = (
        "__str__",
        "court",
        "request_type",
    )
    list_filter = (
        "status",
        "request_type",
    )
    readonly_fields = (
        "date_created",
        "date_modified",
    )
    raw_id_fields = (
        "user",
        "docket",
        "recap_document",
    )


@admin.register(PacerHtmlFiles)
class PacerHtmlFilesAdmin(CursorPaginatorAdmin):
    list_display = (
        "__str__",
        "upload_type",
        "date_created",
    )
    readonly_fields = (
        "date_created",
        "date_modified",
    )


admin.site.register(FjcIntegratedDatabase)
