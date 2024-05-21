from rest_framework import serializers
from rest_framework.serializers import ValidationError

from cl.search.api_serializers import OpinionClusterSerializer


class CitationAPIRequestSerializer(serializers.Serializer):
    text = serializers.CharField(required=False, max_length=64_000)
    reporter = serializers.CharField(max_length=100, required=False)
    volume = serializers.IntegerField(required=False)
    page = serializers.CharField(required=False)

    def validate(self, data):
        reporter = data.get("reporter")
        text = data.get("text")
        volume = data.get("volume")
        page = data.get("page")
        citation_or_reporter_provided = any([reporter, text])

        # make sure users provide either a reporter or a text citation.
        if not all([len(data), citation_or_reporter_provided]):
            raise ValidationError(
                {
                    "non_field_errors": [
                        "Either 'text' or 'reporter' is required."
                    ]
                }
            )

        # Enforces mutually exclusive fields: reporter and text.
        if all([reporter, text]):
            raise ValidationError(
                {
                    "non_field_errors": [
                        "Invalid request. Provide either a 'text' or 'reporter', not both."
                    ]
                }
            )

        # Make sure users provide a volume and a page when they use the
        # reporter field to look up citations.
        if reporter and not all([volume, page]):
            errors = {}
            if not volume:
                errors["volume"] = ["This field is required."]
            if not page:
                errors["page"] = ["This field is required."]
            raise ValidationError(errors)

        return data


class CitationAPIResponseSerializer(serializers.Serializer):
    citation = serializers.CharField()
    normalized_citations = serializers.ListField(child=serializers.CharField())
    start_index = serializers.IntegerField()
    end_index = serializers.IntegerField()
    status = serializers.IntegerField()
    error_message = serializers.CharField(required=False, default="")
    clusters = serializers.SerializerMethodField(required=False)

    def get_clusters(self, obj):
        if "clusters" not in obj:
            return []

        return OpinionClusterSerializer(
            obj["clusters"],
            many=True,
            context={"request": self.context["request"]},
        ).data
