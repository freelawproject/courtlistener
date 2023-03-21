from admin_cursor_paginator import CursorPaginatorAdmin
from django.contrib import admin

from cl.lasc.models import Docket, DocumentFiled
from cl.lib.admin import AdminTweaksMixin


class Base(CursorPaginatorAdmin, AdminTweaksMixin):
    readonly_fields = (
        "date_created",
        "date_modified",
    )
    raw_id_fields = ("docket",)


class DocumentFiledInline(admin.TabularInline, AdminTweaksMixin):
    model = DocumentFiled


@admin.register(Docket)
class DocketAdmin(Base):
    inlines = [
        DocumentFiledInline,
    ]

    raw_id_fields = ()

    search_fields = ("docket_number",)
