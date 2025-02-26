from admin_cursor_paginator import CursorPaginatorAdmin

from cl.citations.models import UnmatchedCitation
from django.contrib import admin

@admin.register(UnmatchedCitation)
class UnmatchedCitationAdmin(CursorPaginatorAdmin):
    list_display = (
        "__str__",
        "type",
    )
    list_filter = ("type", "status")
    search_fields = (
        "volume",
        "reporter",
        "page",
    )
