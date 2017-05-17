from rest_framework import serializers

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
        exclude = ('uploader',)
