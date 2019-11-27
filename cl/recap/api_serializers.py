from django.db.models import Q

from juriscraper.lib.exceptions import PacerLoginException
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from cl.lib.pacer_session import get_or_cache_pacer_cookies
from cl.recap.models import FjcIntegratedDatabase, ProcessingQueue, \
    UPLOAD_TYPE, PacerFetchQueue
from cl.search.models import Court, RECAPDocument, Docket


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
        if attrs['upload_type'] in [UPLOAD_TYPE.DOCKET,
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
                ]) | Q(pk__in=['cit', 'jpml', 'uscfc']),
            ).values_list('pk', flat=True)
            if attrs['court'].pk not in district_court_ids:
                raise ValidationError("%s is not a district or bankruptcy "
                                      "court ID. Did you mean to use the "
                                      "upload_type for appellate dockets?" %
                                      attrs['court'])

        if attrs['upload_type'] == UPLOAD_TYPE.APPELLATE_DOCKET:
            # Appellate court dockets. Is the court valid?
            appellate_court_ids = Court.objects.filter(
                Q(jurisdiction__in=[Court.FEDERAL_APPELLATE]) |
                    # Court of Appeals for Veterans Claims uses appellate PACER
                    Q(pk__in=['cavc']),
            ).values_list('pk', flat=True)
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


class PacerFetchQueueSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(
        default=serializers.CurrentUserDefault(),
    )
    court = serializers.PrimaryKeyRelatedField(
        queryset=Court.objects.filter(
            jurisdiction__in=Court.FEDERAL_JURISDICTIONS
        ),
        html_cutoff=500,  # Show all values in HTML view.
        required=False,
    )
    docket = serializers.PrimaryKeyRelatedField(
        queryset=Docket.objects.all(),
        required=False,
    )
    recap_document = serializers.PrimaryKeyRelatedField(
        queryset=RECAPDocument.objects.all(),
        required=False,
    )
    pacer_username = serializers.CharField(write_only=True)
    pacer_password = serializers.CharField(write_only=True)

    class Meta:
        model = PacerFetchQueue
        exclude = (
            'user',  # Private
        )
        read_only_fields = (
            'date_created',
            'date_modified',
            'date_completed',
            'status',
            'message',
        )

    def validate(self, attrs):
        # Is it a good court value?
        district_court_ids = Court.objects.filter(
            Q(jurisdiction__in=[
                Court.FEDERAL_DISTRICT,
                Court.FEDERAL_BANKRUPTCY,
            ]) | Q(pk__in=['cit', 'jpml', 'uscfc']),
        ).values_list('pk', flat=True)
        if attrs.get('court') and attrs['court'].pk not in district_court_ids:
            raise ValidationError("Invalid court id: %s" % attrs['court'].pk)

        # Docket validations
        if attrs.get('pacer_case_id') and not attrs.get('court'):
            # If a pacer_case_id is included, is a court also?
            raise ValidationError("Cannot use 'pacer_case_id' parameter "
                                  "without 'court' parameter.")
        if attrs.get('docket_number') and not attrs.get('court'):
            # If a docket_number is included, is a court also?
            raise ValidationError("Cannot use 'docket_number' parameter "
                                  "without 'court' parameter.")
        if attrs.get('show_terminated_parties') and not \
                attrs.get('show_parties_and_counsel'):
            raise ValidationError(
                "You've requested to show_terminated_parties parties while "
                "show_parties_and_counsel is False. To show terminated "
                "parties, you must also request showing parties and counsel "
                "generally."
            )

        # PDF validations
        if attrs.get('recap_document'):
            rd = attrs['recap_document']
            if rd.is_available:
                raise ValidationError(
                    "Cannot fetch a PDF for recap_document %s. That document "
                    "is already marked as available in our database "
                    "(is_available = True)." % rd.pk
                )

        # Do the PACER credentials work?
        try:
            _ = get_or_cache_pacer_cookies(
                attrs['user'].pk,
                username=attrs.pop('pacer_username'),
                password=attrs.pop('pacer_password'),
            )
        except PacerLoginException as e:
            raise ValidationError("PacerLoginException: %s" % e.message)

        return attrs


class PacerDocIdLookUpSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = RECAPDocument
        fields = ('pacer_doc_id', 'filepath_local', 'id',)


class FjcIntegratedDatabaseSerializer(serializers.HyperlinkedModelSerializer):

    class Meta:
        model = FjcIntegratedDatabase
        fields = '__all__'
