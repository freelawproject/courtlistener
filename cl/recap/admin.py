"""Django admin configuration for RECAP processing queues and the FJC IDB."""

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
from cl.recap.tasks import (
    do_recap_document_fetch,
    process_scotus_email,
    process_texas_email,
)


@admin.register(ProcessingQueue)
class ProcessingQueueAdmin(CursorPaginatorAdmin):
    """Admin for RECAP upload processing queue items."""

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
    """Admin for PACER fetch requests."""

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
    """Admin for stored PACER HTML files, listed with their upload type."""

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
    """Reprocess the selected email processing queue items.

    SCOTUS emails and Texas state emails are queued for processing; other
    state emails are skipped, and the rest are fetched as the recap-email
    user.
    """
    recap_email_user = User.objects.get(username="recap-email")
    for epq in queryset:
        if epq.source == EmailSource.SCOTUS:
            process_scotus_email.delay(epq.pk)
        elif epq.source == EmailSource.STATE:
            if is_texas_court(epq.court_id):
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
    """Admin for recap.email processing queue items, with a reprocess action."""

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
