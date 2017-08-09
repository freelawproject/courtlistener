from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from cl.recap.models import ProcessingQueue
from cl.search.models import Court


class ProcessingQueueSerializer(serializers.ModelSerializer):
    uploader = serializers.HiddenField(
        default=serializers.CurrentUserDefault(),
    )
    court = serializers.PrimaryKeyRelatedField(
        queryset=Court.objects.filter(jurisdiction__in=['FB', 'FD', 'F', 'FBP',
                                                        'FS']),
        html_cutoff=500,  # Show all values in HTML view.
    )

    class Meta:
        model = ProcessingQueue
        exclude = (
            'uploader',  # Private
        )
        read_only_fields = (
            'error_message',
            'status',
            'uploader',
        )
        extra_kwargs = {'filepath_local': {'write_only': True}}

    def validate(self, attrs):
        # No numbers on Dockets
        if attrs['upload_type'] == ProcessingQueue.DOCKET:
            numbers_not_blank = any([attrs.get('pacer_doc_id'),
                                     attrs.get('document_number'),
                                     attrs.get('attachment_number')])
            if numbers_not_blank:
                raise ValidationError("PACER document ID, document number and "
                                      "attachment number must be blank for "
                                      "docket uploads.")
        return attrs
