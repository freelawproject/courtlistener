from admin_cursor_paginator import CursorPaginatorAdmin
from django.contrib import admin, messages
from django.contrib.auth.models import User
from django.utils.translation import ngettext

from cl.lib.model_helpers import is_texas_court
from cl.recap.models import (
    EmailProcessingQueue,
    EmailSource,
    FjcIntegratedDatabase,
    PacerFetchQueue,
    PacerHtmlFiles,
    ProcessingQueue,
)
from cl.recap.tasks import do_recap_document_fetch, process_texas_email


@admin.register(ProcessingQueue)
class ProcessingQueueAdmin(CursorPaginatorAdmin):
    list_display = (
        "__str__",
        "court",
        "pacer_case_id",
        "document_number",
        "attachment_number",
        "date_created",
    )
    list_filter = ("status", "date_created")
    search_help_text = "Search ProcessingQueues by pacer_case_id or court__pk."
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
    list_display = ("__str__", "court", "request_type", "date_created")
    list_filter = ("status", "request_type", "date_created")
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


@admin.action(description="Reprocess selected recap.emails")
def reprocess_failed_epq(modeladmin, request, queryset):
    recap_email_user = User.objects.get(username="recap-email")
    for epq in queryset:
        if epq.source == EmailSource.STATE:
            if is_texas_court(epq.court):
                process_texas_email.delay(epq.pk)
        else:
            do_recap_document_fetch(epq, recap_email_user)

    modeladmin.message_user(
        request,
        ngettext(
            "%d epq was successfully reprocessed.",
            "%d epqs were successfully reprocessed.",
            queryset.count(),
        )
        % queryset.count(),
        messages.SUCCESS,
    )


@admin.register(EmailProcessingQueue)
class EmailProcessingQueueAdmin(CursorPaginatorAdmin):
    list_display = ("__str__", "status", "date_created")
    list_filter = ("status", "date_created")
    actions = [reprocess_failed_epq]
    raw_id_fields = ["uploader", "court"]
    exclude = ["recap_documents", "filepath"]
    readonly_fields = (
        "date_created",
        "date_modified",
    )


admin.site.register(FjcIntegratedDatabase)
