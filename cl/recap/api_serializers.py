from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from cl.recap.models import ProcessingQueue
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
        # Dockets shouldn't have these fields completed.
        if attrs['upload_type'] == ProcessingQueue.DOCKET:
            numbers_not_blank = any([attrs.get('pacer_doc_id'),
                                     attrs.get('document_number'),
                                     attrs.get('attachment_number')])
            if numbers_not_blank:
                raise ValidationError("PACER document ID, document number and "
                                      "attachment number must be blank for "
                                      "docket uploads.")
        # PDFs require a pacer_doc_id value.
        if attrs['upload_type'] == ProcessingQueue.PDF:
            if not all([attrs.get('pacer_doc_id'),
                        attrs.get('document_number')]):
                raise ValidationError("Uploaded PDFs must have the "
                                      "pacer_doc_id and document_number fields "
                                      "completed.")
        return attrs


class PacerDocIdLookUpSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = RECAPDocument
        fields = ('pacer_doc_id', 'filepath_local', 'id',)
