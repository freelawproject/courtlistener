from django.contrib import admin

from cl.lasc.models import (
    Action,
    CrossReference,
    Docket,
    DocumentFiled,
    DocumentImage,
    Party,
    Proceeding,
    QueuedCase,
    QueuedPDF,
    TentativeRuling,
)
from cl.lib.admin import AdminTweaksMixin


class Base(admin.ModelAdmin, AdminTweaksMixin):

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


@admin.register(DocumentImage)
class DocumentImageAdmin(Base):
    readonly_fields = (
        "document_map_url",
        "show_url",
        "date_created",
        "date_modified",
    )

    def show_url(self, instance):
        return '<a href="%s">%s</a>' % (
            instance.document_map_url,
            instance.document_map_url,
        )

    show_url.short_description = "URL"
    show_url.allow_tags = True


@admin.register(Action)
@admin.register(CrossReference)
@admin.register(DocumentFiled)
@admin.register(Proceeding)
@admin.register(Party)
@admin.register(TentativeRuling)
@admin.register(QueuedPDF)
class QueuedPDFAdmin(admin.ModelAdmin):
    readonly_fields = (
        "date_created",
        "date_modified",
        "show_url",
    )

    def show_url(self, instance):
        return '<a href="%s">%s</a>' % (
            instance.document_url,
            instance.document_url,
        )

    show_url.short_description = "URL"
    show_url.allow_tags = True


@admin.register(QueuedCase)
class QueuedCaseAdmin(admin.ModelAdmin):
    readonly_fields = (
        "date_created",
        "date_modified",
        "show_url",
    )

    def show_url(self, instance):
        return '<a href="%s">%s</a>' % (instance.case_url, instance.case_url)

    show_url.short_description = "URL"
    show_url.allow_tags = True
