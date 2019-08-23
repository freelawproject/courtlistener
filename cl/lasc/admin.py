from django.contrib import admin
from django.forms import TextInput, Textarea
from django.db import models

from cl.lasc.models import Action, CrossReference, Docket, DocumentFiled, \
    DocumentImage, LASCJSON, LASCPDF, Party, Proceeding, \
    QueuedCase, QueuedPDF, TentativeRuling


class Base(admin.ModelAdmin):
    formfield_overrides = {
        models.CharField: {'widget': TextInput(attrs={'size':'20'})},
        models.TextField: {'widget': Textarea(attrs={'rows':4, 'cols':40})},
    }

    readonly_fields = (
        'date_created',
        'date_modified',
    )

    dates = (
        'date_created',
        'date_modified',
    )

    raw_id_fields = (
        'docket',
    )

    @classmethod
    def add(self, fields):
        return fields + (self.dates)

    @classmethod
    def add_all(self, fields):
        return ("docket",) + fields + (self.dates)

    class Meta:
        abstract = True


class DocumentFiledInline(admin.TabularInline):
    model = DocumentFiled

    formfield_overrides = {
        models.CharField: {'widget': TextInput(attrs={'size':'20'})},
        models.TextField: {'widget': Textarea(attrs={'rows':4, 'cols':40})},
    }


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
    )
    fields = Base.add(fields)

    inlines = [
        DocumentFiledInline,
    ]

    raw_id_fields = ()

    search_fields = (
        'docket_number',
        'case_name',
        'judge_code',
        'courthouse_name',
    )

@admin.register(DocumentFiled)
class DocumentFiledAdmin(Base):
    fields = (
        'document_type',
        'memo',
        'party_str',
        'date_filed',
    )
    fields = Base.add_all(fields)

    search_fields = (
        'document_type',
        'party_str',
    )

@admin.register(DocumentImage)
class DocumentImageAdmin(Base):
    fields = (
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
        'show_url'
    )
    fields = Base.add_all(fields)

    readonly_fields = (
        'document_map_url',
        'show_url',
        'date_created',
        'date_modified',
    )

    def show_url(self, instance):
        return '<a href="%s">%s</a>' % (instance.document_map_url, instance.document_map_url)

    show_url.short_description = 'URL'
    show_url.allow_tags = True

@admin.register(Action)
class ActionFiledAdmin(Base):
    fields = (
        'date_of_action',
        'description',
        'additional_information',
    )
    fields = Base.add_all(fields)

    search_fields = (
        'description',
        'date_of_action',
    )


@admin.register(CrossReference)
class CrossReferenceAdmin(Base):
    fields = (
        'date_cross_reference',
        'cross_reference_type',
        'cross_reference_docket_number',
    )
    fields = Base.add_all(fields)

    search_fields = (
        'cross_reference_docket_number',
    )

@admin.register(Proceeding)
class ProceedingAdmin(Base):
    fields = (
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
    )
    fields = Base.add_all(fields)

    search_fields = (
        'judge_name',
        'event',
    )

@admin.register(Party)
class PartyAdmin(Base):
    fields = (
        'entity_number',
        'party_name',
        'party_flag',
        'party_type_code',
        'party_description',
        'attorney_name',
        'attorney_firm',
    )
    fields = Base.add_all(fields)

@admin.register(TentativeRuling)
class TentativeRulingAdmin(Base):
    fields = (
        'date_hearing',
        'department',
        'ruling',
    )
    fields = Base.add_all(fields)

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
        return '<a href="%s">%s</a>' % (instance.document_url, instance.document_url)

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


@admin.register(LASCJSON)
class LASCJSONAdmin(admin.ModelAdmin):
    fields = (
        'object_id',
        'filepath',
        'upload_type',
        'sha1',
        'date_created',
        'date_modified',
    )
    readonly_fields = (
        'date_created',
        'date_modified',
    )

@admin.register(LASCPDF)
class LASCPDFAdmin(admin.ModelAdmin):
    fields = (
        'object_id',
        'page_count',
        'file_size',
        'plain_text',
        'ocr_status',
        'filepath_local',
        'filepath_ia',
        'ia_upload_failure_count',
        'thumbnail',
        'thumbnail_status',
        'sha1',
        'date_created',
        'date_modified',
    )
    readonly_fields = (
        'date_created',
        'date_modified',
    )
