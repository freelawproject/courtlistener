# coding=utf-8

from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey, \
    GenericRelation
from django.contrib.contenttypes.models import ContentType

from cl.lib.models import AbstractJSON, AbstractPDF


class UPLOAD_TYPE:
    DOCKET = 1
    NAMES = (
        (DOCKET, 'JSON Docket'),
    )


class LASCJSON(AbstractJSON):
    """This is a simple object for holding original JSON content from LASC's
    API. We will use this maintain a copy of all json acquired from LASC which
    is important in the event we need to reparse something.
    """
    upload_type = models.SmallIntegerField(
        help_text="The type of object that is uploaded",
        choices=UPLOAD_TYPE.NAMES,
    )


class LASCPDF(AbstractPDF):
    """This is a simple object for holding original PDF content from LASC's
    API. We will use this maintain a copy of all PDFs acquired from LASC. This
    is important in the event we lose our database.
    """

    content_type = models.ForeignKey(ContentType)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey()

    @property
    def file_contents(self):
        with open(self.filepath_local.path, 'r') as f:
            return f.read().decode('utf-8')

    def print_file_contents(self):
        print(self.file_contents)


class QueuedCases(models.Model):
    """This is a simple table of Cases we have yet to fetch,
    but have a list of from date searching.
    """

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
    internal_case_id = models.CharField(
        help_text="Internal Case Id",
        max_length=300,
        db_index=True,
        blank=True,
    )


class QueuedPdfs(models.Model):
    """This is a simple table of PDFs we have yet to download.
    """

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
    internal_case_id = models.CharField(
        help_text="Internal Case Id"
                  "",
        max_length=300,
        db_index=True,
        blank=True,
    )
    document_id = models.CharField(
        help_text="Internal Document Id",
        max_length=40,
        db_index=True,
        blank=True,
    )

    @property
    def document_url(self):
        return '/'.join(["https://media.lacourt.org/api/AzureApi",
                        self.internal_case_id,
                        self.document_id])


class Docket(models.Model):
    """High-level object to contain all other LASC-related data"""
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
    date_checked = models.DateTimeField(
        help_text="Datetime case was last pulled or checked from LASC",
        null=True,
        blank=True,
        db_index=True,
    )
    date_filed = models.DateField(
        help_text="The date the case was filed",
        null=True,
        blank=True,
    )
    date_disposition = models.DateField(
        help_text="The date the case was disposed by the court",
        null=True,
        blank=True,
    )
    docket_number = models.CharField(
        help_text="Docket number for the case. E.g. 19LBCV00507, "
                  "19STCV28994, or even 30-2017-00900866-CU-AS-CJC.",
        max_length=300,
        db_index=True,
        blank=True,
    )
    district = models.CharField(
        help_text="District is a 2-3 character code representing court "
                  "locations; For Example BUR means Burbank",
        max_length=10,
        blank=True,
    )
    division_code = models.CharField(
        help_text="Division. E.g. civil (CV), civil probate (CP), etc.",
        max_length=10,
        blank=True,
    )
    case_hash = models.CharField(
        help_text="SHA1 Hash of Case Data",
        max_length=128,
    )
    json_document = GenericRelation(
        to='lasc.LASCJSON',
        help_text="JSON files.",
        related_query_name='case_json',
        null=True,
        blank=True,
    )
    disposition_type = models.TextField(
        help_text="Disposition type",
        null=True,
        blank=True
    )
    disposition_type_code = models.TextField(
        help_text="Disposition type code",
        null=True,
        blank=True,
    )
    filing_date_string = models.TextField(
        help_text="The date the case was filed as a string",
        null=True,
        blank=True,
    )
    disposition_date_string = models.TextField(
        help_text="The date the case was disposed by the court as a string",
        null=True,
        blank=True,
    )
    case_type_description = models.TextField(
        help_text="Case Type Description",
        blank=True,
    )
    case_type_code = models.CharField(
        help_text="Case Type Code",
        max_length=10,
        null=True,
    )
    case_title = models.TextField(
        help_text="Case Title",
        blank=True,
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
        help_text="The courthouse name",
        blank=True,
    )
    case_type = models.IntegerField(
        help_text="Case Type Code",
        null=True,
        blank=True,
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

    class Meta:
        index_together = ('docket_number', 'district', 'division_code')

    @property
    def case_id(self):
        return ';'.join([self.docket_number, self.district,
                         self.division_code])


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
        to='lasc.LASCPDF',
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
    )
    date_filed = models.DateTimeField(
        help_text="Date a document was filed as a DateTime object",
    )
    date_filed_string = models.CharField(
        help_text="Date a document was filed as a string",
        max_length=25,
    )
    memo = models.TextField(
        help_text="Memo describing document filed",
        null=True,
        blank=True,
    )
    party = models.TextField(
        help_text="Filing Party",
        null=True,
        blank=True,
    )
    document = models.TextField(
        help_text="Document Type",
        null=True,
        blank=True,
        default='',
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
