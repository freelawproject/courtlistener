from juriscraper.lib.exceptions import PacerLoginException
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from cl.corpus_importer.utils import is_appellate_court
from cl.lib.pacer_session import get_or_cache_pacer_cookies
from cl.recap.models import (
    REQUEST_TYPE,
    UPLOAD_TYPE,
    EmailProcessingQueue,
    FjcIntegratedDatabase,
    PacerFetchQueue,
    ProcessingQueue,
)
from cl.recap.utils import get_court_id_from_fetch_queue
from cl.search.models import Court, Docket, RECAPDocument


class ProcessingQueueSerializer(serializers.ModelSerializer):
    # Powers the RECAP upload endpoint
    uploader = serializers.HiddenField(
        default=serializers.CurrentUserDefault(),
    )
    court = serializers.PrimaryKeyRelatedField(
        queryset=Court.federal_courts.all(),
        html_cutoff=500,  # Show all values in HTML view.
    )
    docket = serializers.HyperlinkedRelatedField(
        many=False,
        read_only=True,
        view_name="docket-detail",
        style={"base_template": "input.html"},
    )
    docket_entry = serializers.HyperlinkedRelatedField(
        many=False,
        read_only=True,
        view_name="docketentry-detail",
        style={"base_template": "input.html"},
    )
    recap_document = serializers.HyperlinkedRelatedField(
        many=False,
        read_only=True,
        view_name="recapdocument-detail",
        style={"base_template": "input.html"},
    )

    class Meta:
        model = ProcessingQueue
        fields = "__all__"
        read_only_fields = (
            "error_message",
            "status",
            "docket",
            "docket_entry",
            "recap_document",
        )
        extra_kwargs = {"filepath_local": {"write_only": True}}

    def validate(self, attrs):
        for attr_name in [
            "pacer_doc_id",
            "pacer_case_id",
            "document_number",
            "attachment_number",
        ]:
            # Regardless of upload type, we don't want values to be set to
            # "undefined"
            if attrs.get(attr_name) == "undefined":
                raise ValidationError(
                    f"'{attr_name}' field cannot have the literal value 'undefined'."
                )

        if attrs["upload_type"] in [
            UPLOAD_TYPE.DOCKET,
            UPLOAD_TYPE.APPELLATE_DOCKET,
            UPLOAD_TYPE.ACMS_DOCKET_JSON,
            UPLOAD_TYPE.CLAIMS_REGISTER,
        ]:
            # Dockets shouldn't have these fields completed.
            numbers_not_blank = any(
                [
                    attrs.get("pacer_doc_id"),
                    attrs.get("document_number"),
                    attrs.get("attachment_number"),
                ]
            )
            if numbers_not_blank:
                raise ValidationError(
                    "PACER document ID, document number and attachment number "
                    "must be blank for docket or claims register uploads."
                )

        if attrs["upload_type"] in [
            UPLOAD_TYPE.DOCKET,
            UPLOAD_TYPE.DOCKET_HISTORY_REPORT,
            UPLOAD_TYPE.CASE_QUERY_PAGE,
            UPLOAD_TYPE.CASE_QUERY_RESULT_PAGE,
        ]:
            # These are district or bankruptcy court dockets. Is the court valid?
            court_ids = (
                Court.federal_courts.district_or_bankruptcy_pacer_courts()
            )
            if not court_ids.filter(pk=attrs["court"].pk).exists():
                raise ValidationError(
                    "{} is not a district or bankruptcy court ID. Did you "
                    "mean to use the upload_type for appellate dockets?".format(
                        attrs["court"]
                    )
                )

        if attrs["upload_type"] == UPLOAD_TYPE.CLAIMS_REGISTER:
            # Only allowed on bankruptcy courts
            bankruptcy_court_ids = (
                Court.federal_courts.bankruptcy_pacer_courts()
            )
            if not bankruptcy_court_ids.filter(pk=attrs["court"].pk).exists():
                raise ValidationError(
                    "{} is not a bankruptcy court ID. Only bankruptcy cases "
                    "should have claims registry pages.".format(attrs["court"])
                )

        if attrs["upload_type"] in [
            UPLOAD_TYPE.APPELLATE_ATTACHMENT_PAGE,
            UPLOAD_TYPE.APPELLATE_DOCKET,
            UPLOAD_TYPE.ACMS_ATTACHMENT_PAGE,
            UPLOAD_TYPE.ACMS_DOCKET_JSON,
            UPLOAD_TYPE.APPELLATE_CASE_QUERY_PAGE,
            UPLOAD_TYPE.APPELLATE_CASE_QUERY_RESULT_PAGE,
        ]:
            # Appellate court dockets. Is the court valid?
            if not is_appellate_court(attrs["court"].pk):
                raise ValidationError(
                    "{} is not an appellate court ID. Did you mean to use the "
                    "upload_type for district dockets?".format(attrs["court"])
                )

        if attrs["upload_type"] == UPLOAD_TYPE.PDF:
            # PDFs require pacer_doc_id and document_number values.
            if not all(
                [attrs.get("pacer_doc_id"), attrs.get("document_number")]
            ):
                raise ValidationError(
                    "Uploaded PDFs must have the pacer_doc_id and "
                    "document_number fields completed."
                )

        if attrs["upload_type"] not in [
            UPLOAD_TYPE.PDF,
            UPLOAD_TYPE.APPELLATE_CASE_QUERY_RESULT_PAGE,
            UPLOAD_TYPE.CASE_QUERY_RESULT_PAGE,
        ]:
            # Everything but PDFs and case query result pages require the case
            # ID.
            if not attrs.get("pacer_case_id"):
                raise ValidationError(
                    "PACER case ID is required for for all non-document "
                    "uploads."
                )

            dashes = attrs.get("pacer_case_id").count("-")
            if dashes == 1:
                raise ValidationError(
                    "PACER case ID can not contain a single (-); "
                    "that looks like a docket number."
                )

        return attrs


class EmailProcessingQueueSerializer(serializers.ModelSerializer):
    uploader = serializers.HiddenField(
        default=serializers.CurrentUserDefault(),
    )
    court = serializers.PrimaryKeyRelatedField(
        queryset=Court.federal_courts.all(),
        html_cutoff=500,  # Show all values in HTML view.
        required=True,
    )
    mail = serializers.JSONField(write_only=True)
    receipt = serializers.JSONField(write_only=True)
    recap_document = serializers.HyperlinkedRelatedField(
        many=False,
        read_only=True,
        view_name="recapdocument-detail",
        style={"base_template": "input.html"},
    )

    class Meta:
        model = EmailProcessingQueue
        fields = "__all__"
        read_only_fields = (
            "error_message",
            "status",
            "recap_documents",
        )

    def validate(self, attrs):
        court_id = attrs["court"].pk
        mail = attrs["mail"]
        receipt = attrs["receipt"]

        all_court_ids = Court.federal_courts.all_pacer_courts()
        if not all_court_ids.filter(pk=court_id).exists():
            raise ValidationError(
                f"{attrs['court'].pk} is not a PACER court ID."
            )

        for attr_name in [
            "message_id",
            "timestamp",
            "source",
            "destination",
            "headers",
        ]:
            if (
                mail.get(attr_name) is None
                or mail.get(attr_name) == "undefined"
            ):
                raise ValidationError(
                    f"The JSON value at key 'mail' should include '{attr_name}'."
                )

        for attr_name in ["timestamp", "recipients"]:
            if (
                receipt.get(attr_name) is None
                or receipt.get(attr_name) == "undefined"
            ):
                raise ValidationError(
                    f"The JSON value at key 'receipt' should include '{attr_name}'."
                )

        return attrs

    def create(self, validated_data):
        validated_data.pop("mail", None)
        validated_data.pop("receipt", None)
        return super().create(validated_data)


class PacerFetchQueueSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    court = serializers.PrimaryKeyRelatedField(
        queryset=Court.federal_courts.all(),
        html_cutoff=500,  # Show all values in HTML view.
        required=False,
    )
    docket = serializers.PrimaryKeyRelatedField(
        queryset=Docket.objects.all(), required=False
    )
    recap_document = serializers.PrimaryKeyRelatedField(
        queryset=RECAPDocument.objects.all(), required=False
    )
    pacer_username = serializers.CharField(write_only=True)
    pacer_password = serializers.CharField(write_only=True)
    client_code = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = PacerFetchQueue
        fields = "__all__"
        read_only_fields = (
            "date_created",
            "date_modified",
            "date_completed",
            "status",
            "message",
        )

    def validate(self, attrs):
        # Validates the input attributes, ensuring the request has all required
        # elements.
        match attrs["request_type"]:
            case REQUEST_TYPE.DOCKET:
                # Validation for docket requests.  Requires at least one of
                # docket ID, docket number/court pair, or PACER case ID.
                if not any(
                    [
                        attrs.get("docket"),
                        attrs.get("docket_number"),
                        attrs.get("pacer_case_id"),
                    ]
                ):
                    raise ValidationError(
                        "For docket requests, please provide one of the "
                        "following: a docket ID ('docket'), a docket number "
                        "('docket_number') and court pair, or a PACER case ID "
                        "('pacer_case_id') and court pair."
                    )
            case REQUEST_TYPE.PDF | REQUEST_TYPE.ATTACHMENT_PAGE:
                # Attachment page and PDF validation
                if not attrs.get("recap_document"):
                    raise ValidationError(
                        "recap_document is a required field for attachment page "
                        "and PDF fetches."
                    )

        # Docket validations
        if attrs.get("pacer_case_id") and not attrs.get("court"):
            # If a pacer_case_id is included, is a court also?
            raise ValidationError(
                "Cannot use 'pacer_case_id' parameter "
                "without 'court' parameter."
            )

        if attrs.get("pacer_case_id"):
            dashes = attrs.get("pacer_case_id").count("-")
            if dashes == 1:
                raise ValidationError(
                    "PACER case ID can not contain a single (-); "
                    "that looks like a docket number."
                )

        if attrs.get("docket_number") and not attrs.get("court"):
            # If a docket_number is included, is a court also?
            raise ValidationError(
                "Cannot use 'docket_number' parameter "
                "without 'court' parameter."
            )

        if (
            attrs.get("pacer_case_id")
            and not attrs.get("docket_number")
            and is_appellate_court(attrs.get("court").pk)
        ):
            # The user is trying to purchase an appellate docket using only the
            # PACER case ID, which is not supported.
            raise ValidationError(
                "Purchases of appellate dockets using a PACER case ID are not "
                "currently supported. Please use the docket number instead."
            )

        court_id = get_court_id_from_fetch_queue(attrs)
        if (
            attrs.get("de_number_end") or attrs.get("de_number_start")
        ) and is_appellate_court(court_id):
            raise ValidationError(
                "Docket entry filtering by number is not supported for "
                "appellate courts. Use date range filtering with "
                "'de_date_start' and 'de_date_end' instead."
            )

        if attrs.get("show_terminated_parties") and not attrs.get(
            "show_parties_and_counsel"
        ):
            raise ValidationError(
                "You've requested to show_terminated_parties parties while "
                "show_parties_and_counsel is False. To show terminated "
                "parties, you must also request showing parties and counsel "
                "generally."
            )

        # Is it a good court value?
        valid_court_ids = Court.federal_courts.all_pacer_courts()
        if not valid_court_ids.filter(pk=court_id).exists():
            if attrs.get("court"):
                error_message = (f"Invalid court id: {court_id}",)
            else:
                error_message = (
                    f"Purchases from court {court_id} are not supported"
                )
            raise ValidationError(error_message)

        # PDF validations
        if attrs["request_type"] == REQUEST_TYPE.PDF:
            rd = attrs["recap_document"]
            if rd.is_available:
                raise ValidationError(
                    f"Cannot fetch a PDF for recap_document {rd.pk}. That document "
                    "is already marked as available in our database "
                    "(is_available = True)."
                )

        # Do the PACER credentials work?
        try:
            _ = get_or_cache_pacer_cookies(
                attrs["user"].pk,
                username=attrs.pop("pacer_username"),
                password=attrs.pop("pacer_password"),
                client_code=attrs.pop("client_code", None),
            )
        except PacerLoginException as e:
            raise ValidationError(f"PacerLoginException: {e}")

        return attrs


class PacerDocIdLookUpSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = RECAPDocument
        fields = (
            "pacer_doc_id",
            "filepath_local",
            "acms_document_guid",
            "id",
        )


class FjcIntegratedDatabaseSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = FjcIntegratedDatabase
        fields = "__all__"
