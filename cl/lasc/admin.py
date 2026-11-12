"""Django admin configuration for LASC dockets."""

from admin_cursor_paginator import CursorPaginatorAdmin
from django.contrib import admin

from cl.lasc.models import Docket, DocumentFiled
from cl.lib.admin import AdminTweaksMixin


class Base(CursorPaginatorAdmin, AdminTweaksMixin):
    """Shared admin settings for LASC models."""

    readonly_fields = (
        "date_created",
        "date_modified",
    )
    raw_id_fields = ("docket",)


class DocumentFiledInline(admin.TabularInline, AdminTweaksMixin):
    """Inline for a docket's filed documents."""

    model = DocumentFiled


@admin.register(Docket)
class DocketAdmin(Base):
    """Admin for LASC dockets, showing their filed documents inline."""

    inlines = [
        DocumentFiledInline,
    ]

    raw_id_fields = ()

    search_fields = ("docket_number",)
