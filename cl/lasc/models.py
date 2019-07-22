# coding=utf-8
import os
import re, datetime

from django.db import models
from django.contrib.sites.models import Site

class LASC(models.Model):

    """Rows from the LASC Date Search report table converted to rows in the DB."""

    Courthouse = models.TextField(max_length=50)
    DispDate = models.DateTimeField(null=True, blank=True)
    DispType = models.TextField(null=True, blank=True)
    FilingDate = models.DateTimeField()
    District = models.CharField(max_length=10)
    CaseTypeDescription = models.TextField()
    CaseTypeCode = models.CharField(max_length=5)
    FilingDateString = models.TextField()
    DispDateString = models.TextField()
    CaseTitle = models.TextField()
    DispTypeCode = models.TextField(null=True, blank=True)
    DivisionCode = models.CharField(max_length=10)
    JudgeCode = models.CharField( max_length=10, null=True, blank=True)
    JudicialOfficer = models.TextField( null=True, blank=True)
    InternalCaseID = models.CharField(max_length=30)
    CaseNumber = models.CharField(max_length=30)

    Status = models.TextField(null=True, blank=True)
    CaseType = models.IntegerField(null=True, blank=True)
    DispositionType = models.TextField(null=True, blank=True)
    CaseID = models.TextField(null=True, blank=True)
    StatusDate = models.TextField(null=True, blank=True)
    StatusCode = models.TextField(null=True, blank=True)

    date_added = models.DateTimeField(null=True, blank=True)
    date_updated = models.DateTimeField(null=True, blank=True)

class DocumentImages(models.Model):

    caseNumber = models.TextField()
    pageCount = models.IntegerField()
    IsPurchaseable = models.TextField()
    createDateString = models.TextField()
    documentType = models.TextField()
    docFilingDateString = models.TextField()
    documentURL = models.TextField()
    createDate = models.TextField()
    IsInCart = models.BooleanField()
    OdysseyID = models.TextField()
    IsDownloadable = models.BooleanField()
    documentTypeID = models.TextField()
    docId = models.TextField()
    description = models.TextField()
    volume = models.TextField()
    appId = models.TextField()
    IsViewable = models.BooleanField()
    securityLevel = models.TextField()
    IsEmailable = models.BooleanField()
    imageTypeId = models.TextField()
    IsPurchased = models.BooleanField()
    docFilingDate = models.DateTimeField()
    docPart = models.TextField()


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
    # "docPart": PACERFreeDocumentRow

    LASC = models.ForeignKey(LASC)


class RegisterOfActions(models.Model):

    IsPurchaseable = models.BooleanField()
    Description = models.TextField()
    PageCount = models.IntegerField()
    AdditionalInformation = models.TextField()
    RegisterOfActionDateString = models.TextField()
    IsPurchased = models.BooleanField()
    FilenetID = models.TextField()
    IsEmailable = models.BooleanField()
    IsViewable = models.BooleanField()
    OdysseyID = models.TextField()
    IsInCart = models.BooleanField()
    RegisterOfActionDate = models.TextField()
    IsDownloadable = models.BooleanField()

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

    LASC = models.ForeignKey(LASC, related_name='registers')

    pass

class CaseHistory(models.Model):
    pass

class CrossReferences(models.Model):
    # "CrossReferenceDateString": "11/08/2001",
    # "CrossReferenceDate": "2001-11-07T23:00:00-08:00",
    # "CrossReferenceCaseNumber": "37-2011-0095551-",
    # "CrossReferenceTypeDescription": "Coordinated Case(s)"

    CrossReferenceDateString = models.TextField()
    CrossReferenceDate = models.TextField()
    CrossReferenceCaseNumber = models.TextField()
    CrossReferenceTypeDescription = models.TextField()

    LASC = models.ForeignKey(LASC)

    pass

class Parties(models.Model):
    EntityNumber = models.TextField()
    PartyFlag = models.TextField()
    DateOfBirthString = models.TextField()
    CaseNumber = models.TextField()
    District = models.TextField()
    CRSPartyCode = models.TextField(null=True, blank=True)
    DateOfBirth = models.TextField()
    AttorneyFirm = models.TextField()
    CivasCXCNumber = models.TextField()
    AttorneyName = models.TextField()
    PartyDescription = models.TextField()
    DivisionCode = models.TextField()
    PartyTypeCode = models.TextField()
    Name = models.TextField()

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

    LASC = models.ForeignKey(LASC)

    pass

class ProbateNotes(models.Model):
    pass

class PastProceedings(models.Model):

    ProceedingDateString = models.TextField()
    CourtAlt = models.TextField()
    CaseNumber = models.TextField()
    District = models.TextField()
    AMPM = models.TextField()
    Memo = models.TextField()
    Address = models.TextField()
    ProceedingRoom = models.TextField()
    PartyDescription = models.TextField()
    ProceedingDate = models.TextField()
    Result = models.TextField()
    ProceedingTime = models.TextField()
    Judge = models.TextField()
    CourthouseName = models.TextField()
    DivisionCode = models.TextField()
    Event = models.TextField()

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

    LASC = models.ForeignKey(LASC)

    pass

class FutureProceedings(models.Model):

    ProceedingDateString = models.TextField()
    CourtAlt = models.TextField()
    CaseNumber = models.TextField()
    District = models.TextField()
    AMPM = models.TextField()
    Memo = models.TextField()
    Address = models.TextField()
    ProceedingRoom = models.TextField()
    ProceedingDate = models.TextField()
    Result = models.TextField()
    ProceedingTime = models.TextField()
    Judge = models.TextField()
    CourthouseName = models.TextField()
    DivisionCode = models.TextField()
    Event = models.TextField()

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

    LASC = models.ForeignKey(LASC)

    pass

class TentativeRulings(models.Model):
    CaseNumber = models.TextField()
    HearingDate = models.TextField()
    LocationID = models.TextField()
    Ruling = models.TextField()
    Department = models.TextField()
    CreationDateString = models.TextField()
    CreationDate = models.TextField()
    HearingDateString = models.TextField()


    # "CaseNumber": "VC065473",
    # "HearingDate": "2019-07-11T00:00:00-07:00",
    # "LocationID": "SE ",
    # "Ruling": "SUPER LONG HTML"
    # "Department": "SEC",
    # "CreationDateString": "07/10/2019",
    # "CreationDate": "2019-07-10T14:51:33-07:00",
    # "HearingDateString": "07/11/2019"
    LASC = models.ForeignKey(LASC)

    pass

class DocumentsFiled(models.Model):

    CaseNumber = models.CharField( max_length=20)
    Memo = models.TextField(null=True, blank=True)
    DateFiled = models.TextField()
    DateFiledString = models.CharField( max_length=25)
    Party = models.TextField()
    Document = models.TextField(
        help_text="The cluster that the opinion is a part of"
    )

    # "CaseNumber": "18STCV02953",
    # "Memo": null,
    # "DateFiled": "2019-06-07T00:00:00-07:00",
    # "DateFiledString": "06/07/2019",
    # "Party": "Angel Ortiz Hernandez (Defendant)",
    # "Document": "Answer"
    LASC = models.ForeignKey(LASC)

    pass
