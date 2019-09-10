from django.contrib import admin
from cl.lib.admin import CSSAdminMixin
from cl.lasc.models import Action, CrossReference, Docket, DocumentFiled, \
    DocumentImage, Party, Proceeding, \
    QueuedCase, QueuedPDF, TentativeRuling


class Base(admin.ModelAdmin, CSSAdminMixin):

    readonly_fields = (
        'date_created',
        'date_modified',
    )
    raw_id_fields = (
        'docket',
    )


class DocumentFiledInline(admin.TabularInline, CSSAdminMixin):
    model = DocumentFiled


@admin.register(Docket)
class DocketAdmin(Base):
    fields = (
        'docket_number',
        'district',
        'division_code',
        'date_disposition',
        'disposition_type',
        'disposition_type_code',
        'case_type_str',
        'case_type_code',
        'case_name',
        'judge_code',
        'judge_name',
        'courthouse_name',
        'date_status',
        'status_code',
        'status_str',
        'date_checked',
        'date_filed',
        'date_created',
        'date_modified',
    )

    inlines = [
        DocumentFiledInline,
    ]

    raw_id_fields = ()

    search_fields = (
        'docket_number',
    )


@admin.register(DocumentFiled)
class DocumentFiledAdmin(Base):
    fields = (
        'docket',
        'document_type',
        'memo',
        'party_str',
        'date_filed',
        'date_created',
        'date_modified',
    )


@admin.register(DocumentImage)
class DocumentImageAdmin(Base):
    fields = (
        'docket',
        'doc_id',
        'page_count',
        'document_type',
        'document_type_code',
        'image_type_id',
        'app_id',
        'odyssey_id',
        'is_downloadable',
        'security_level',
        'description',
        'volume',
        'doc_part',
        'is_available',
        'document_map_url',
        'show_url',
        'date_created',
        'date_modified',
    )

    readonly_fields = (
        'document_map_url',
        'show_url',
        'date_created',
        'date_modified',
    )

    def show_url(self, instance):
        return '<a href="%s">%s</a>' % (instance.document_map_url,
                                        instance.document_map_url)

    show_url.short_description = 'URL'
    show_url.allow_tags = True


@admin.register(Action)
class ActionFiledAdmin(Base, CSSAdminMixin):
    fields = (
        'docket',
        'date_of_action',
        'description',
        'additional_information',
        'date_created',
        'date_modified',
    )


@admin.register(CrossReference)
class CrossReferenceAdmin(Base):
    fields = (
        'docket',
        'date_cross_reference',
        'cross_reference_type',
        'cross_reference_docket_number',
        'date_created',
        'date_modified',
    )


@admin.register(Proceeding)
class ProceedingAdmin(Base):
    fields = (
        'docket',
        'courthouse_name',
        'address',
        'event',
        'result',
        'judge_name',
        'memo',
        'date_proceeding',
        'am_pm',
        'proceeding_time',
        'proceeding_room',
        'past_or_future',
        'date_created',
        'date_modified',
    )


@admin.register(Party)
class PartyAdmin(Base):
    fields = (
        'docket',
        'entity_number',
        'party_name',
        'party_flag',
        'party_type_code',
        'party_description',
        'attorney_name',
        'attorney_firm',
        'date_created',
        'date_modified',
    )


@admin.register(TentativeRuling)
class TentativeRulingAdmin(Base):
    fields = (
        'docket'
        'date_hearing',
        'department',
        'ruling',
        'date_created',
        'date_modified',
    )


@admin.register(QueuedPDF)
class QueuedPDFAdmin(admin.ModelAdmin):
    fields = (
        'document_id',
        'internal_case_id',
        'date_created',
        'date_modified',
        'show_url',
    )
    readonly_fields = (
        'date_created',
        'date_modified',
        'show_url',
    )

    def show_url(self, instance):
        return '<a href="%s">%s</a>' % (instance.document_url,
                                        instance.document_url)

    show_url.short_description = 'URL'
    show_url.allow_tags = True


@admin.register(QueuedCase)
class QueuedCaseAdmin(admin.ModelAdmin):
    fields = (
        'internal_case_id',
        'judge_code',
        'case_type_code',
        'date_created',
        'date_modified',
        'show_url',
    )
    readonly_fields = (
        'date_created',
        'date_modified',
        'show_url',
    )

    def show_url(self, instance):
        return '<a href="%s">%s</a>' % (instance.case_url, instance.case_url)

    show_url.short_description = 'URL'
    show_url.allow_tags = True
