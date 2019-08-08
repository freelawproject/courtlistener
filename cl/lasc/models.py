# coding=utf-8

from django.db import models
from django.contrib.contenttypes.fields import GenericRelation

class LASC(models.Model):

    """ ..."""

    case_id = models.CharField(max_length=30,
                               help_text="Internal Case ID = "
                                         "{Combination of Case Number; District; Division Code}",)


    starred = models.BooleanField(default=False,
                                  help_text="",)

    full_data_model = models.BooleanField(default=False,
                                          help_text="Indicates if the case has been scraped beyond "
                                                    "Basic Date Search information",)

    date_added = models.DateTimeField(null=True,
                                      blank=True,
                                      help_text="Date Time the Case was added to the system",)

    date_checked = models.DateTimeField(null=True,
                                        blank=True,
                                        help_text="Datetime case was last checked",)

    date_modified = models.DateTimeField(null=True,
                                         blank=True,
                                         help_text="Datetime a value changed in the dataset",)

    case_hash = models.CharField(max_length=128,
                                 default="",
                                 help_text="MD5 Hash Enocding hexabit to compare new / old data")


    json_document = GenericRelation('lib.JSONFile',
                                    help_text="JSON files.",
                                    related_query_name='case_json',
                                    null=True,
                                    blank=True
                                    )


class CaseInformation(models.Model):
    LASC = models.ForeignKey(LASC, on_delete=models.CASCADE)

    case_id = models.TextField(null=True,
                               blank=True,
                               help_text="Internal Case ID",)

    case_number = models.CharField(max_length=30,
                                   help_text="Court Case Number")

    disposition_type = models.TextField(null=True, blank=True)

    disposition_type_code = models.TextField(null=True, blank=True)

    filing_date = models.DateField(null=True,
                                   blank=True,
                                   help_text="The date the case was filed as a Date")

    filing_date_string = models.TextField(null=True,
                                          blank=True,
                                          help_text="The date the case was filed as a String")

    disposition_date = models.DateField(null=True,
                                        blank=True,
                                        help_text="The date the case was disposed by the court as a Date")

    disposition_date_string = models.TextField(null=True,
                                               blank=True,
                                               help_text="The date the case was disposed by the court as a String")

    district = models.CharField(max_length=10,
                                help_text="District is a 2-3 character code representing court locations; "
                                          "For Example BUR means Burbank")

    case_type_description = models.TextField(help_text="Case Type Description")

    case_type_code = models.CharField(max_length=5,
                                      help_text="Case Type Code")

    case_title = models.TextField(help_text="The Case Title")

    division_code = models.CharField(max_length=10)

    judge_code = models.CharField(max_length=10,
                                  null=True,
                                  blank=True,
                                  help_text="Internal Jude Code assigned to the case")

    judicial_officer = models.TextField(null=True,
                                        blank=True,
                                        help_text="The judge that the case was assigned to, as a string")

    courthouse = models.TextField(max_length=50,
                                  help_text="The Courthouse the case resides")

    case_type = models.IntegerField(null=True,
                                    blank=True,
                                    help_text="Case Type Code") #may delete

    status = models.TextField(null=True,
                              blank=True,
                              help_text="The status of the case, as a string")

    status_date = models.TextField(null=True,
                                   blank=True,
                                   help_text="Date status was updated as a string")

    status_code = models.TextField(null=True,
                                   blank=True,
                                   help_text="Court Status Code associated with current status")


class DocumentImages(models.Model):

    """ ..."""

    LASC = models.ForeignKey(LASC, on_delete=models.CASCADE)

    case_number = models.TextField(help_text="Case Number associated with this document")
    page_count = models.IntegerField(help_text="Page count for this document")

    document_type = models.TextField(null=True, blank=True)
    document_url = models.TextField(help_text="") #always blank but we can make it from the database.....

    create_date = models.TextField(help_text="The date the document was created in the system as a Date object")
    create_date_string = models.TextField(help_text="The date the document was created in the system as a String")

    doc_filing_date = models.DateField(help_text="The date the document was filed in the system as a Date object")
    doc_filing_date_string = models.TextField(help_text="The date the document was filed in the system as a String object")

    image_type_id = models.TextField(help_text="")
    app_id = models.TextField(help_text="ID for filing application, if any.") #Is this the App that was used to file the document?  California have multiple options?
    doc_id = models.TextField(help_text="Internal Document ID")
    document_type_id = models.TextField(help_text="")

    odyssey_id = models.TextField(null=True, blank=True)

    is_downloadable = models.BooleanField(default=True, help_text="Is the document downloadable by Courtlistener as a BOOL")
    is_viewable = models.BooleanField(default=True, help_text="Is the document viewable by Courtlistener as a BOOL")
    is_emailable = models.BooleanField(default=True, help_text="Is the document emailable by Courtlistener as a BOOL")
    is_purchaseable = models.TextField(default=True, help_text="Is the document available to purchase by Courtlistener as a BOOL")
    is_purchased = models.BooleanField(default=True, help_text="Has the document been purchased by Courtlistener as a BOOL")

    downloaded = models.BooleanField(default=False, help_text="Has the document been downloaded as a BOOL")

    security_level = models.TextField(null=True, blank=True, help_text="Document security level")

    description = models.TextField(null=True, blank=True, help_text="Document description")
    volume = models.TextField(null=True, blank=True, help_text="Document Volume")
    doc_part = models.TextField(null=True, blank=True, help_text="Document Part?")

    # is_in_cart = models.BooleanField(default=True, help_text="Is the document downloadable by Courtlistener as a BOOL")


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



class RegisterOfActions(models.Model):

    """ ..."""

    LASC = models.ForeignKey(LASC, related_name='registers', on_delete=models.CASCADE)

    description = models.TextField(help_text="Short description of the document")
    additional_information = models.TextField(help_text="Additional information stored as HTML")
    register_of_action_date_string = models.TextField(help_text="Date of Register of Action as a String")
    register_of_action_date = models.DateTimeField(help_text="Date of Register of Action as a Date Object")


    # page_count = models.IntegerField()
    # is_purchaseable = models.BooleanField()
    # is_emailable = models.BooleanField()
    # is_viewable = models.BooleanField()
    # is_in_cart = models.BooleanField()
    # is_downloadable = models.BooleanField()
    # is_purchased = models.BooleanField()

    # filenet_id = models.TextField(help_text="")
    # odyssey_id = models.TextField(help_text="")


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


    pass


class CrossReferences(models.Model):

    LASC = models.ForeignKey(LASC, on_delete=models.CASCADE)

    cross_reference_date_string = models.TextField(help_text="Cross Reference date as a String")        #--->"11/08/2001",
    cross_reference_date = models.DateField(help_text="Cross reference date as a Date Object")               #"2001-11-07T23:00:00-08:00",
    cross_reference_case_number = models.TextField(help_text="Cross Reference Case Number")        #"37-2011-0095551-",
    cross_reference_type_description = models.TextField(help_text="Cross Reference short description")   #"Coordinated Case(s)"


class Parties(models.Model):

    LASC = models.ForeignKey(LASC, on_delete=models.CASCADE)

    case_number = models.TextField(help_text="Case Number")
    district = models.TextField(help_text="Court District")
    division_code = models.TextField(help_text="Court Division ")
    attorney_name = models.TextField(help_text="Attorney Name")
    attorney_firm = models.TextField(help_text="Attorney Firm")
    entity_number = models.TextField(help_text="Order entity/party joined cases system as String")
    party_flag = models.TextField(help_text="Court Code representing party")
    party_type_code = models.TextField(help_text="Court code representing party position")
    party_description = models.TextField(help_text="Description of the party")
    name = models.TextField(help_text="Full name of the party")

    # civas_cxc_number = models.TextField(help_text="")
    # crs_party_code = models.TextField(null=True, blank=True)
    # date_of_birth = models.TextField(help_text="")
    # date_of_birth_string = models.TextField(help_text="")

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



class PastProceedings(models.Model):

    LASC = models.ForeignKey(LASC, on_delete=models.CASCADE)

    court_alt = models.TextField(help_text="")
    case_number = models.TextField(help_text="Court Case Number")
    district = models.TextField(help_text="Court District")
    am_pm = models.TextField(help_text="Was the proceeding in the AM or PM")
    memo = models.TextField(help_text="Memo about the past proceeding")
    address = models.TextField(help_text="Address of the past proceeding")

    proceeding_date_string = models.TextField(help_text="Date of Past Proceeding as a string")
    proceeding_room = models.TextField(help_text="The court room of the past proceeding")
    proceeding_date = models.TextField(help_text="Date of the past proceeding as a date object")
    proceeding_time = models.TextField(help_text="Time of the past proceeding")

    result = models.TextField(help_text="Result of the past proceeding")
    judge = models.TextField(help_text="Judge in the past proceeding")
    courthouse_name = models.TextField(help_text="Courthouse name for the past proceeding")
    division_code = models.TextField(help_text="Courthouse Division {ex. CV = Civil}")
    event = models.TextField(help_text="Event that occurred {ex. Jury Trial}")


    # "ProceedingDateString": "05/20/2019",
    # "CourtAlt": "",
    # "CaseNumber": "JCCP4674",
    # "District": "",
    # "AMPM": "AM",
    # "Memo": "",
    # "Address": "",
    # "ProceedingRoom": "Legacy",
    # "ProceedingDate": "2019-05-20T00:00:00-07:00",
    # "Result": "Not Held - Vacated by Court",
    # "ProceedingTime": "09:00",
    # "Judge": "",
    # "CourthouseName": "",
    # "DivisionCode": "",
    # "Event": "Jury Trial"



class FutureProceedings(models.Model):

    LASC = models.ForeignKey(LASC, on_delete=models.CASCADE)

    court_alt = models.TextField(help_text="")
    case_number = models.TextField(help_text="Court Case Number")
    district = models.TextField(help_text="Court District")
    am_pm = models.TextField(help_text="Was the proceeding in the AM or PM")
    memo = models.TextField(help_text="Memo about the past proceeding")
    address = models.TextField(help_text="Address of the past proceeding")

    proceeding_date = models.TextField(help_text="Date of the past proceeding as a date object")
    proceeding_date_string = models.TextField(help_text="Date of Past Proceeding as a string")
    proceeding_room = models.TextField(help_text="The court room of the past proceeding")
    proceeding_time = models.TextField(help_text="Time of the past proceeding in HH:MM string")

    result = models.TextField(help_text="Result of the past proceeding")
    judge = models.TextField(help_text="Judge in the past proceeding")
    courthouse_name = models.TextField(help_text="Courthouse name for the past proceeding")
    division_code = models.TextField(help_text="Courthouse Division {ex. CV = Civil}")
    event = models.TextField(help_text="Event that occurred {ex. Jury Trial}")


    # "ProceedingDateString": "04/13/2020",
    # "CourtAlt": "SS ",
    # "CaseNumber": "18STCV02953",
    # "District": "SS ",
    # "AMPM": "AM",
    # "Memo": "",
    # "Address": "SS ",
    # "ProceedingRoom": "5",
    # "ProceedingDate": "2020-04-13T00:00:00-07:00",
    # "Result": "",
    # "ProceedingTime": "10:00",
    # "Judge": "",
    # "CourthouseName": "Spring Street Courthouse",
    # "DivisionCode": "CV",
    # "Event": "Final Status Conference"



class TentativeRulings(models.Model):

    LASC = models.ForeignKey(LASC, on_delete=models.CASCADE)

    case_number = models.TextField(help_text="Case number")
    location_id = models.TextField(help_text="Internal court code for location")
    department = models.TextField(help_text="Internal court code for department")
    ruling = models.TextField(help_text="The court decision in HTML format as long string")
    creation_date = models.TextField(help_text="Date the ruling was decided as a date object")
    creation_date_string = models.TextField(help_text="Date the ruling was added to the system as a string")
    hearing_date = models.DateTimeField(help_text="")
    hearing_date_string = models.TextField(help_text="")



    # "CaseNumber": "VC065473",
    # "HearingDate": "2019-07-11T00:00:00-07:00",
    # "LocationID": "SE ",
    # "Ruling": "SUPER LONG HTML"
    # "Department": "SEC",
    # "CreationDateString": "07/10/2019",
    # "CreationDate": "2019-07-10T14:51:33-07:00",
    # "HearingDateString": "07/11/2019"


class DocumentsFiled(models.Model):

    LASC = models.ForeignKey(LASC, on_delete=models.CASCADE)

    case_number = models.CharField(max_length=20, help_text="Case Number associated with the filed document")
    date_filed = models.DateTimeField(help_text="Date a document was filed as a DateTime object")
    date_filed_string = models.CharField(max_length=25, help_text="Date a document was filed as a string")

    memo = models.TextField(null=True, blank=True, help_text="Memo describing document filed")
    party = models.TextField(null=True, blank=True, help_text="Name of the Party responsible for the filed document")

    document = models.TextField(
        null=True, blank=True,
        default='',
        help_text="Document Type"
    )


    # "CaseNumber": "18STCV02953",
    # "Memo": null,
    # "DateFiled": "2019-06-07T00:00:00-07:00",
    # "DateFiledString": "06/07/2019",
    # "Party": "Angel Ortiz Hernandez (Defendant)",
    # "Document": "Answer"

class CaseHistory(models.Model):
    """This will probably be removed"""

    pass
