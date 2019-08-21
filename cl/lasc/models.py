# coding=utf-8

from django.db import models
from django.contrib.contenttypes.fields import GenericRelation

class Docket(models.Model):

    """ ..."""

    case_id = models.CharField(
        max_length=30,
        help_text="Internal Case ID = "
                  "{Combination of Case Number; District; Division Code}",
    )
    full_data_model = models.BooleanField(
        default=False,
        help_text="Indicates if the case has been scraped beyond "
                  "Basic Date Search information",
    )
    date_checked = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Datetime case was last checked",
    )
    date_created = models.DateTimeField(
        help_text="The time when this item was created",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified",
        auto_now=True,
        db_index=True,
    )
    case_hash = models.CharField(
        max_length=128,
        help_text="SHA1 Hash of Case Data"
    )
    json_document = GenericRelation(
        to='lib.LASCJSON',
        help_text="JSON files.",
        related_query_name='case_json',
        null=True,
        blank=True,
    )


class CaseInformation(models.Model):
    Docket = models.ForeignKey(
        Docket,
        on_delete=models.CASCADE,
    )
    case_id = models.TextField(
        null=True,
        blank=True,
        help_text="Internal Case ID",
    )
    case_number = models.CharField(
        max_length=30,
        help_text="Court Case Number"
    )
    disposition_type = models.TextField(
        null=True,
        blank=True
    )
    disposition_type_code = models.TextField(
        null=True,
        blank=True
    )
    filing_date = models.DateField(
        null=True,
        blank=True,
        help_text="The date the case was filed as a date",
    )
    filing_date_string = models.TextField(
        null=True,
        blank=True,
        help_text="The date the case was filed as a string",
    )
    disposition_date = models.DateField(
        null=True,
        blank=True,
        help_text="The date the case was disposed by the court as a date",
    )
    disposition_date_string = models.TextField(
        null=True,
        blank=True,
        help_text="The date the case was disposed by the court as a string",
    )
    district = models.CharField(
        max_length=10,
        help_text="District is a 2-3 character code representing court locations; "
                  "For Example BUR means Burbank",
    )
    case_type_description = models.TextField(
        help_text="Case Type Description",
    )
    case_type_code = models.CharField(
        max_length=5,
        help_text="Case Type Code",
    )
    case_title = models.TextField(
        help_text="Case Title",
    )
    division_code = models.CharField(
        max_length=10,
        help_text="Division",
    )
    judge_code = models.CharField(
        max_length=10,
        null=True,
        blank=True,
        help_text="Internal Jude Code assigned to the case",
    )
    judicial_officer = models.TextField(
        null=True,
        blank=True,
        help_text="The judge that the case was assigned to, as a string",
    )
    courthouse = models.TextField(
        max_length=50,
        help_text="The courthouse name",
    )
    case_type = models.IntegerField(
        null=True,
        blank=True,
        help_text="Case Type Code",
    )
    status = models.TextField(
        null=True,
        blank=True,
        help_text="The status of the case, as a string",
    )
    status_date = models.TextField(
        null=True,
        blank=True,
        help_text="Date status was updated as a string",
    )
    status_code = models.TextField(
        null=True,
        blank=True,
        help_text="Court Status Code associated with current status",
    )
    date_created = models.DateTimeField(
        help_text="The time when this item was created",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified.",
        auto_now=True,
        db_index=True,
    )


class DocumentImages(models.Model):

    """
        # caseNumber
        # pageCount
        # IsPurchaseable
        # createDateString
        # documentType
        # "docFilingDateString": "06/07/2019",
        # "documentURL": "",
        # "createDate": "2019-06-07T00:00:00-07:00",
        # "IsInCart": false,
        # "OdysseyID": "",
        # "IsDownloadable": true,
        # "documentTypeID": "",
        # "docId": "1769824611",
        # "description": "Answer",
        # "volume": "",
        # "appId": "",
        # "IsViewable": true,
        # "securityLevel": 0,
        # "IsEmailable": false,
        # "imageTypeId": 3,
        # "IsPurchased": true,
        # "docFilingDate": "2019-06-07T00:00:00-07:00",
        # "docPart":
    """

    Docket = models.ForeignKey(
        Docket,
        on_delete=models.CASCADE,
        null=True
    )
    page_count = models.IntegerField(
        help_text="Page count for this document",
    )
    document_type = models.TextField(
        null=True,
        blank=True,
        help_text="Type of Document Code",
    )
    document_url = models.TextField(
        help_text="The document URL {MAP Credentials required}",
    )
    create_date = models.TextField(
        help_text="The date the document was created in the system as a date object",
    )
    create_date_string = models.TextField(
        help_text="The date the document was created in the system as a string",
    )
    doc_filing_date = models.DateField(
        help_text="The date the document was filed in the system as a date object",
    )
    doc_filing_date_string = models.TextField(
        help_text="The date the document was filed in the system as a string object",
    )
    image_type_id = models.TextField(
        help_text="Image Type ID",
    )
    app_id = models.TextField(
        help_text="ID for filing application, if any.",
    )
    doc_id = models.TextField(
        help_text="Internal Document ID",
    )
    document_type_id = models.TextField(
        help_text="Document Type ID",
    )
    odyssey_id = models.TextField(
        null=True,
        blank=True,
    )
    is_downloadable = models.BooleanField(
        default=True,
        help_text="Is the document downloadable by Courtlistener as a BOOL",
    )
    is_viewable = models.BooleanField(
        default=True,
        help_text="Is the document viewable by Courtlistener as a BOOL",
    )
    is_emailable = models.BooleanField(
        default=True,
        help_text="Is the document emailable by Courtlistener as a BOOL",
    )
    is_purchaseable = models.TextField(
        default=True,
        help_text="Is the document available to purchase by Courtlistener as a BOOL",
    )
    is_purchased = models.BooleanField(
        default=True,
        help_text="Has the document been purchased by Courtlistener as a BOOL",
    )
    downloaded = models.BooleanField(
        default=False,
        help_text="Has the document been downloaded as a BOOL",
    )
    security_level = models.TextField(
        null=True,
        blank=True,
        help_text="Document security level",
    )
    description = models.TextField(
        null=True,
        blank=True,
        help_text="Document description",
    )
    volume = models.TextField(
        null=True,
        blank=True,
        help_text="Document Volume",
    )
    doc_part = models.TextField(
        null=True,
        blank=True,
        help_text="Document Part",
    )
    date_created = models.DateTimeField(
        help_text="The time when this item was created",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified.",
        auto_now=True,
        db_index=True,
    )
    pdf_document = GenericRelation(
        to='lib.LASCPDF',
        help_text="PDF document.",
        related_query_name='case_pdf',
        null=True,
        blank=True,
    )


class RegisterOfActions(models.Model):

    """
        # "IsPurchaseable": false,
        # "Description": "Answer",
        # "PageCount": -1,
        # "AdditionalInformation": "<ul><li>Party: Angel Ortiz Hernandez (Defendant)</li></ul>",
        # "RegisterOfActionDateString": "06/07/2019",
        # "IsPurchased": false,
        # "FilenetID": "",
        # "IsEmailable": false,
        # "IsViewable": false,
        # "OdysseyID": "",
        # "IsInCart": false,
        # "RegisterOfActionDate": "2019-06-07T00:00:00-07:00",
        # "IsDownloadable": false
    """

    Docket = models.ForeignKey(
        Docket,
        on_delete=models.CASCADE,
        null=True
    )
    description = models.TextField(
        help_text="Short description of the document",
    )
    additional_information = models.TextField(
        help_text="Additional information stored as HTML",
    )
    register_of_action_date_string = models.TextField(
        help_text="Date of Register of Action as a string",
    )
    register_of_action_date = models.DateTimeField(
        help_text="Date of Register of Action as a Date Object",
    )
    date_created = models.DateTimeField(
        help_text="The time when this item was created",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified.",
        auto_now=True,
        db_index=True,
    )


class CrossReferences(models.Model):

    """
    cross_reference_date_string: "11/08/2001"
    cross_reference_date : 2001-11-07T23:00:00-08:00
    cross_reference_case_number: 37-2011-0095551-
    cross_reference_type_description:  Coordinated Case(s)
    """

    Docket = models.ForeignKey(
        Docket,
        on_delete=models.CASCADE,
        null=True
    )
    cross_reference_date_string = models.TextField(
        help_text="Cross Reference date as a String",
        null=True,
    )
    cross_reference_date = models.DateTimeField(
        help_text="Cross reference date as a Date Object",
        null=True,
    )
    cross_reference_case_number = models.TextField(
        help_text="Cross Reference Case Number",
        null=True,
    )
    cross_reference_type_description = models.TextField(
        help_text="Cross Reference short description",
        null=True,
    )
    date_created = models.DateTimeField(
        help_text="The time when this item was created",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified.",
        auto_now=True,
        db_index=True,
    )


class Parties(models.Model):

    """
    # "EntityNumber": "3",
    # "PartyFlag": "L",
    # "DateOfBirthString": "",
    # "CaseNumber": "18STCV02953",
    # "District": "",
    # "CRSPartyCode": null,
    # "DateOfBirth": "0001-01-01T00:00:00-08:00",
    # "AttorneyFirm": "",
    # "CivasCXCNumber": "",
    # "AttorneyName": "",
    # "PartyDescription": "Defendant",
    # "DivisionCode": "CV",
    # "PartyTypeCode": "D",
    # "Name": "HERNANDEZ ANGEL ORTIZ AKA ANGEL HERNANDEZ"

    """

    Docket = models.ForeignKey(
        Docket,
        on_delete=models.CASCADE,
        null=True,
    )


    attorney_name = models.TextField(
        help_text="Attorney Name",
    )
    attorney_firm = models.TextField(
        help_text="Attorney Firm",
    )
    entity_number = models.TextField(
        help_text="Order entity/party joined cases system as String",
    )
    party_flag = models.TextField(
        help_text="Court Code representing party",
    )
    party_type_code = models.TextField(
        help_text="Court code representing party position",
    )
    party_description = models.TextField(
        help_text="Description of the party",
    )
    name = models.TextField(
        help_text="Full name of the party",
    )
    date_created = models.DateTimeField(
        help_text="The time when this item was created",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified.",
        auto_now=True,
        db_index=True,
    )


class PastManager(models.Manager):
    def get_queryset(self):
        return super(PastManager, self).get_queryset().filter(past_or_future=1)


class FutureManager(models.Manager):
    def get_queryset(self):
        return super(FutureManager, self).get_queryset().filter(past_or_future=2)


class Proceedings(models.Model):
    PAST = 1
    FUTURE  = 2
    TIME_CHOICES = (
        (PAST, "Things in the past"),
        (FUTURE, "Things in the future"),
    )

    Docket = models.ForeignKey(
        Docket,
        on_delete=models.CASCADE,
        null=True,
    )
    am_pm = models.TextField(
        help_text="Was the proceeding in the AM or PM",
    )
    memo = models.TextField(
        help_text="Memo about the past proceeding",
    )
    address = models.TextField(
        help_text="Address of the past proceeding",
    )
    proceeding_date = models.TextField(
        help_text="Date of the past proceeding as a date object",
    )
    proceeding_date_string = models.TextField(
        help_text="Date of Past Proceeding as a string",
    )
    proceeding_room = models.TextField(
        help_text="The court room of the past proceeding",
    )
    proceeding_time = models.TextField(
        help_text="Time of the past proceeding in HH:MM string",
    )
    result = models.TextField(
        help_text="Result of the past proceeding",
    )
    judge = models.TextField(
        help_text="Judge in the past proceeding",
    )
    courthouse_name = models.TextField(
        help_text="Courthouse name for the past proceeding",
    )
    division_code = models.TextField(
        help_text="Courthouse Division {ex. CV = Civil}",
    )
    event = models.TextField(
        help_text="Event that occurred {ex. Jury Trial}",
    )
    date_created = models.DateTimeField(
        help_text="The time when this item was created",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified.",
        auto_now=True,
        db_index=True,
    )
    past_or_future = models.SmallIntegerField(
        choices=TIME_CHOICES,
        null=True,
        blank=True,
        help_text="Is this event in the Past {1} or Future {2}"
    )
    past_objects = PastManager()
    future_objects = FutureManager()
    objects = models.Manager() # The default manager.


class TentativeRulings(models.Model):
    """
    Sample data taken from random cases.

    "CaseNumber": "VC065473",
    "HearingDate": "2019-07-11T00:00:00-07:00",
    "LocationID": "SE ",
    "Ruling": "SUPER LONG HTML"
    "Department": "SEC",
    "CreationDateString": "07/10/2019",
    "CreationDate": "2019-07-10T14:51:33-07:00",
    "HearingDateString": "07/11/2019"
    """
    Docket = models.ForeignKey(
        Docket,
        on_delete=models.CASCADE,
        null=True,
    )
    case_number = models.TextField(
        help_text="Case number",
    )
    location_id = models.TextField(
        help_text="Internal court code for location",
    )
    department = models.TextField(
        help_text="Internal court code for department",
    )
    ruling = models.TextField(
        help_text="The court ruling as HTML",
    )
    creation_date = models.DateTimeField(
        help_text="Date the ruling was decided as a date object",
    )
    creation_date_string = models.TextField(
        help_text="Date the ruling was added to the system as a string",
    )
    hearing_date = models.DateTimeField(
        help_text="",
    )
    hearing_date_string = models.TextField(
        help_text="",
    )
    date_created = models.DateTimeField(
        help_text="The time when this item was created",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified.",
        auto_now=True,
        db_index=True,
    )

class DocumentsFiled(models.Model):
    """
    # "CaseNumber": "18STCV02953",
    # "Memo": null,
    # "DateFiled": "2019-06-07T00:00:00-07:00",
    # "DateFiledString": "06/07/2019",
    # "Party": "Angel Ortiz Hernandez (Defendant)",
    # "Document": "Answer"]
    """
    Docket = models.ForeignKey(
        Docket,
        on_delete=models.CASCADE,
        null=True,
    )
    # case_number = models.CharField(max_length=20, help_text="Case Number associated with the filed document")

    date_filed = models.DateTimeField(
        help_text="Date a document was filed as a DateTime object",
    )
    date_filed_string = models.CharField(
        max_length=25,
        help_text="Date a document was filed as a string",
    )
    memo = models.TextField(
        null=True,
        blank=True,
        help_text="Memo describing document filed",
    )
    party = models.TextField(
        null=True,
        blank=True,
        help_text="Filing Party",
    )
    document = models.TextField(
        null=True, blank=True,
        default='',
        help_text="Document Type"
    )
    date_created = models.DateTimeField(
        help_text="The time when this item was created",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified.",
        auto_now=True,
        db_index=True,
    )
