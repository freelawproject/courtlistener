from django.db.models import Q
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from cl.recap.models import ProcessingQueue, UPLOAD_TYPE
from cl.search.models import Court, RECAPDocument


class ProcessingQueueSerializer(serializers.ModelSerializer):
    uploader = serializers.HiddenField(
        default=serializers.CurrentUserDefault(),
    )
    court = serializers.PrimaryKeyRelatedField(
        queryset=Court.objects.filter(
            jurisdiction__in=Court.FEDERAL_JURISDICTIONS
        ),
        html_cutoff=500,  # Show all values in HTML view.
    )
    docket = serializers.HyperlinkedRelatedField(
        many=False,
        read_only=True,
        view_name='docket-detail',
        style={'base_template': 'input.html'},
    )
    docket_entry = serializers.HyperlinkedRelatedField(
        many=False,
        read_only=True,
        view_name='docketentry-detail',
        style={'base_template': 'input.html'}
    )
    recap_document = serializers.HyperlinkedRelatedField(
        many=False,
        read_only=True,
        view_name='recapdocument-detail',
        style={'base_template': 'input.html'}
    )

    class Meta:
        model = ProcessingQueue
        exclude = (
            'uploader',  # Private
        )
        read_only_fields = (
            'error_message',
            'status',
            'docket',
            'docket_entry',
            'recap_document',
        )
        extra_kwargs = {'filepath_local': {'write_only': True}}

    def validate(self, attrs):
        if attrs['upload_type'] == in [UPLOAD_TYPE.DOCKET,
                                       UPLOAD_TYPE.APPELLATE_DOCKET]:
            # Dockets shouldn't have these fields completed.
            numbers_not_blank = any([attrs.get('pacer_doc_id'),
                                     attrs.get('document_number'),
                                     attrs.get('attachment_number')])
            if numbers_not_blank:
                raise ValidationError("PACER document ID, document number and "
                                      "attachment number must be blank for "
                                      "docket uploads.")

        if attrs['upload_type'] in [UPLOAD_TYPE.DOCKET,
                                    UPLOAD_TYPE.DOCKET_HISTORY_REPORT]:
            # These are district court dockets. Is the court valid?
            district_court_ids = Court.objects.filter(
                Q(jurisdiction__in=[
                    Court.FEDERAL_DISTRICT,
                    Court.FEDERAL_BANKRUPTCY,
                ]) | Q(pk__in=['uscfc', 'cit']),
            ).values_list('pk', flat=True)
            if attrs['court'].pk not in district_court_ids:
                raise ValidationError("%s is not a district or bankruptcy "
                                      "court ID. Did you mean to use the "
                                      "upload_type for appellate dockets?" %
                                      attrs['court'])

        if attrs['upload_type'] == UPLOAD_TYPE.APPELLATE_DOCKET:
            # Appellate court dockets. Is the court valid?
            appellate_court_ids = Court.objects.filter(jurisdiction__in=[
                Court.FEDERAL_APPELLATE,
            ])
            if attrs['court'].pk not in appellate_court_ids:
                raise ValidationError("%s is not an appellate court ID. Did "
                                      "you mean to use the upload_type for "
                                      "district dockets?" % attrs['court'])

        elif attrs['upload_type'] == UPLOAD_TYPE.PDF:
            # PDFs require pacer_doc_id and document_number values.
            if not all([attrs.get('pacer_doc_id'),
                        attrs.get('document_number')]):
                raise ValidationError("Uploaded PDFs must have the "
                                      "pacer_doc_id and document_number "
                                      "fields completed.")

        if attrs['upload_type'] != UPLOAD_TYPE.PDF:
            # Everything but PDFs require the case ID.
            if not attrs.get('pacer_case_id'):
                raise ValidationError("PACER case ID is required for for all "
                                      "non-document uploads.")

        return attrs


class PacerDocIdLookUpSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = RECAPDocument
        fields = ('pacer_doc_id', 'filepath_local', 'id',)
