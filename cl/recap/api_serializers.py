from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from cl.recap.models import ProcessingQueue, PDF, DOCKET
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
        if attrs['upload_type'] == DOCKET:
            # Dockets shouldn't have these fields completed.
            numbers_not_blank = any([attrs.get('pacer_doc_id'),
                                     attrs.get('document_number'),
                                     attrs.get('attachment_number')])
            if numbers_not_blank:
                raise ValidationError("PACER document ID, document number and "
                                      "attachment number must be blank for "
                                      "docket uploads.")
        elif attrs['upload_type'] == PDF:
            # PDFs require a pacer_doc_id value.
            if not attrs.get('pacer_doc_id'):
                raise ValidationError("Uploaded PDFs must have the "
                                      "pacer_doc_id field completed.")

        if attrs['upload_type'] != PDF:
            # Everything but PDFs require the case ID.
            if not attrs.get('pacer_case_id'):
                raise ValidationError("PACER case ID is required for for all "
                                      "non-document uploads.")

        return attrs


class PacerDocIdLookUpSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = RECAPDocument
        fields = ('pacer_doc_id', 'filepath_local', 'id',)
