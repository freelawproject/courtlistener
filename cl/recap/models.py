from django.contrib.auth.models import User
from django.db import models

from cl.lib.model_helpers import make_path
from cl.lib.models import AbstractDateTimeModel, AbstractFile
from cl.lib.storage import IncrementingAWSMediaStorage, S3PrivateUUIDStorage
from cl.recap.constants import DATASET_SOURCES, NOO_CODES, NOS_CODES
from cl.search.models import Court, Docket, DocketEntry, RECAPDocument


class UPLOAD_TYPE:
    DOCKET = 1
    ATTACHMENT_PAGE = 2
    PDF = 3
    DOCKET_HISTORY_REPORT = 4
    APPELLATE_DOCKET = 5
    APPELLATE_ATTACHMENT_PAGE = 6
    IA_XML_FILE = 7
    CASE_REPORT_PAGE = 8
    CLAIMS_REGISTER = 9
    DOCUMENT_ZIP = 10
    SES_EMAIL = 11
    CASE_QUERY_PAGE = 12
    APPELLATE_CASE_QUERY_PAGE = 13
    CASE_QUERY_RESULT_PAGE = 14
    APPELLATE_CASE_QUERY_RESULT_PAGE = 15
    NAMES = (
        (DOCKET, "HTML Docket"),
        (ATTACHMENT_PAGE, "HTML attachment page"),
        (PDF, "PDF"),
        (DOCKET_HISTORY_REPORT, "Docket history report"),
        (APPELLATE_DOCKET, "Appellate HTML docket"),
        (APPELLATE_ATTACHMENT_PAGE, "Appellate HTML attachment page"),
        (IA_XML_FILE, "Internet Archive XML docket"),
        (CASE_REPORT_PAGE, "Case report (iquery.pl) page"),
        (CLAIMS_REGISTER, "Claims register page"),
        (DOCUMENT_ZIP, "Zip archive of RECAP Documents"),
        (SES_EMAIL, "Email in the SES storage format"),
        (CASE_QUERY_PAGE, "Case query page"),
        (APPELLATE_CASE_QUERY_PAGE, "Appellate Case query page"),
        (CASE_QUERY_RESULT_PAGE, "Case query result page"),
        (APPELLATE_CASE_QUERY_RESULT_PAGE, "Appellate Case query result page"),
    )


def make_recap_processing_queue_path(instance, filename):
    return make_path("recap_processing_queue", filename)


def make_recap_data_path(instance, filename):
    return make_path("recap-data", filename)


def make_recap_email_processing_queue_aws_path(instance, filename: str) -> str:
    return f"recap-email/{filename}"


class PacerHtmlFiles(AbstractFile, AbstractDateTimeModel):
    """This is a simple object for holding original HTML content from PACER

    We use this object to make sure that for every item we receive from users,
    we can go back and re-parse it one day if we have to. This becomes
    essential as we do more and more data work where we're purchasing content.
    If we don't keep an original copy, a bug could be devastating.
    """

    filepath = models.FileField(
        help_text="The path of the original data from PACER.",
        upload_to=make_recap_data_path,
        storage=S3PrivateUUIDStorage(),
        max_length=150,
    )
    upload_type = models.SmallIntegerField(
        help_text="The type of object that is uploaded",
        choices=UPLOAD_TYPE.NAMES,
    )


class PROCESSING_STATUS:
    ENQUEUED = 1
    SUCCESSFUL = 2
    FAILED = 3
    IN_PROGRESS = 4
    QUEUED_FOR_RETRY = 5
    INVALID_CONTENT = 6
    NEEDS_INFO = 7
    NAMES = (
        (ENQUEUED, "Awaiting processing in queue."),
        (SUCCESSFUL, "Item processed successfully."),
        (FAILED, "Item encountered an error while processing."),
        (IN_PROGRESS, "Item is currently being processed."),
        (QUEUED_FOR_RETRY, "Item failed processing, but will be retried."),
        (INVALID_CONTENT, "Item failed validity tests."),
        (NEEDS_INFO, "There was insufficient metadata to complete the task."),
    )


class ProcessingQueue(AbstractDateTimeModel):
    """Where we store each RECAP upload."""

    court = models.ForeignKey(
        Court,
        help_text="The court where the upload was from",
        related_name="recap_processing_queue",
        on_delete=models.RESTRICT,
    )
    uploader = models.ForeignKey(
        User,
        help_text="The user that uploaded the item to RECAP.",
        related_name="recap_processing_queue",
        # Normal accounts don't upload, so if you've been given access, for now
        # at least, you don't get to delete your account.
        on_delete=models.RESTRICT,
    )
    pacer_case_id = models.CharField(
        help_text="The cased ID provided by PACER.",
        max_length=100,
        db_index=True,
        blank=True,
    )
    pacer_doc_id = models.CharField(
        help_text="The ID of the document in PACER.",
        max_length=32,  # Same as in RECAP
        blank=True,
        db_index=True,
    )
    document_number = models.BigIntegerField(
        help_text="The docket entry number for the document.",
        blank=True,
        null=True,
    )
    attachment_number = models.SmallIntegerField(
        help_text="If the file is an attachment, the number is the attachment "
        "number on the docket.",
        blank=True,
        null=True,
    )
    filepath_local = models.FileField(
        help_text="The path of the uploaded file.",
        upload_to=make_recap_processing_queue_path,
        storage=S3PrivateUUIDStorage(),
        max_length=1000,
    )
    status = models.SmallIntegerField(
        help_text="The current status of this upload. Possible values "
        "are: %s"
        % ", ".join(
            ["(%s): %s" % (t[0], t[1]) for t in PROCESSING_STATUS.NAMES]
        ),
        default=PROCESSING_STATUS.ENQUEUED,
        choices=PROCESSING_STATUS.NAMES,
        db_index=True,
    )
    upload_type = models.SmallIntegerField(
        help_text="The type of object that is uploaded",
        choices=UPLOAD_TYPE.NAMES,
    )
    error_message = models.TextField(
        help_text="Any errors that occurred while processing an item",
        blank=True,
    )
    debug = models.BooleanField(
        help_text="Are you debugging? Debugging uploads will be validated, "
        "but not saved to the database.",
        default=False,
    )

    # Post process fields
    docket = models.ForeignKey(
        Docket,
        help_text="The docket that was created or updated by this request.",
        null=True,
        on_delete=models.SET_NULL,
    )
    docket_entry = models.ForeignKey(
        DocketEntry,
        help_text="The docket entry that was created or updated by this "
        "request, if applicable. Only applies to PDFs uploads.",
        null=True,
        on_delete=models.SET_NULL,
    )
    recap_document = models.ForeignKey(
        RECAPDocument,
        help_text="The document that was created or updated by this request, "
        "if applicable. Only applies to PDFs uploads.",
        null=True,
        on_delete=models.SET_NULL,
    )

    def __str__(self) -> str:
        if self.upload_type in [
            UPLOAD_TYPE.DOCKET,
            UPLOAD_TYPE.DOCKET_HISTORY_REPORT,
            UPLOAD_TYPE.APPELLATE_DOCKET,
            UPLOAD_TYPE.DOCUMENT_ZIP,
        ]:
            return "ProcessingQueue %s: %s case #%s (%s)" % (
                self.pk,
                self.court_id,
                self.pacer_case_id,
                self.get_upload_type_display(),
            )
        elif self.upload_type == UPLOAD_TYPE.PDF:
            return "ProcessingQueue: %s: %s.%s.%s.%s (%s)" % (
                self.pk,
                self.court_id,
                self.pacer_case_id or None,
                self.document_number or None,
                self.attachment_number or 0,
                self.get_upload_type_display(),
            )
        else:
            return f"ProcessingQueue: {self.pk} ({self.get_upload_type_display()})"

    class Meta:
        permissions = (
            ("has_recap_upload_access", "Can upload documents to RECAP."),
        )

    @property
    def file_contents(self) -> str:
        with open(self.filepath_local.path, "r") as f:
            return f.read()

    def print_file_contents(self) -> None:
        print(self.file_contents)


class EmailProcessingQueue(AbstractDateTimeModel):
    """Where @recap.email emails go when received by the API"""

    uploader = models.ForeignKey(
        User,
        help_text="The user that sent in the email for processing.",
        related_name="recap_email_processing_queue",
        # Normal users won't be uploading things to this API. ∴, if you've
        # uploaded to it, your account is too special to delete.
        on_delete=models.RESTRICT,
    )
    court = models.ForeignKey(
        Court,
        help_text="The court where the upload was from",
        related_name="recap_email_processing_queue",
        on_delete=models.RESTRICT,
    )
    message_id = models.TextField(
        help_text="The S3 message identifier, used to pull the file in the processing tasks.",
        default=None,
    )
    destination_emails = models.JSONField(
        help_text="The emails that received the notification.", default=list
    )
    filepath = models.FileField(
        help_text="The S3 filepath to the email and receipt stored as JSON text.",
        upload_to=make_recap_email_processing_queue_aws_path,
        storage=IncrementingAWSMediaStorage(),
        max_length=300,
        null=True,
    )
    status = models.SmallIntegerField(
        help_text="The current status of this upload. Possible values "
        "are: %s"
        % ", ".join(
            ["(%s): %s" % (t[0], t[1]) for t in PROCESSING_STATUS.NAMES]
        ),
        default=PROCESSING_STATUS.ENQUEUED,
        choices=PROCESSING_STATUS.NAMES,
        db_index=True,
    )
    status_message = models.TextField(
        help_text="Any errors that occurred while processing an item",
        blank=True,
    )
    recap_documents = models.ManyToManyField(
        RECAPDocument,
        related_name="recap_email_processing_queue",
        help_text="Document(s) created from the PACER email, processed as a function of this queue.",
    )

    def __str__(self) -> str:
        return f"EmailProcessingQueue: {self.pk} in court {self.court_id}"


class REQUEST_TYPE:
    DOCKET = 1
    PDF = 2
    ATTACHMENT_PAGE = 3

    NAMES = (
        (DOCKET, "HTML Docket"),
        (PDF, "PDF"),
        (ATTACHMENT_PAGE, "Attachment Page"),
    )


class PacerFetchQueue(AbstractDateTimeModel):
    """The queue of requests being made of PACER."""

    date_completed = models.DateTimeField(
        help_text="When the item was completed or errored out.",
        db_index=True,
        null=True,
        blank=True,
    )
    user = models.ForeignKey(
        User,
        help_text="The user that made the request.",
        related_name="pacer_fetch_queue_items",
        # User accounts are not normally deleted; they're made into stubs. So,
        # don't let these accounts get deleted either.
        on_delete=models.RESTRICT,
    )
    status = models.SmallIntegerField(
        help_text="The current status of this request. Possible values "
        "are: %s"
        % ", ".join(
            ["(%s): %s" % (t[0], t[1]) for t in PROCESSING_STATUS.NAMES]
        ),
        default=PROCESSING_STATUS.ENQUEUED,
        choices=PROCESSING_STATUS.NAMES,
        db_index=True,
    )
    request_type = models.SmallIntegerField(
        help_text="The type of object that is requested",
        choices=REQUEST_TYPE.NAMES,
    )
    message = models.TextField(
        help_text="Any messages that may help a user during or after "
        "processing.",
        blank=True,
    )

    #
    # Shared request parameters (can be used across multiple request types)
    #
    court = models.ForeignKey(
        Court,
        help_text="The court where the request will be made",
        related_name="pacer_fetch_queue_items",
        on_delete=models.RESTRICT,
        null=True,
    )

    # PDF and attachment pages use this
    recap_document = models.ForeignKey(
        RECAPDocument,
        help_text="The ID of the RECAP Document in the CourtListener databae "
        "that you wish to fetch or update.",
        related_name="pacer_fetch_queue_items",
        on_delete=models.SET_NULL,
        null=True,
    )

    #
    # Docket request parameters
    #
    docket = models.ForeignKey(
        Docket,
        help_text="The ID of an existing docket object in the CourtListener "
        "database that should be updated.",
        related_name="pacer_fetch_queue_items",
        on_delete=models.SET_NULL,
        null=True,
    )
    pacer_case_id = models.CharField(
        help_text="The case ID provided by PACER for the case to update (must "
        "be used in combination with the court field).",
        max_length=100,
        db_index=True,
        blank=True,
    )
    docket_number = models.CharField(
        help_text="The docket number of a case to update (must be used in "
        "combination with the court field).",
        max_length=50,
        blank=True,
    )
    de_date_start = models.DateField(
        help_text="Only fetch docket entries (de) newer than this date. "
        "Default is 1 Jan. 1960. Timezone appears to be that of the "
        "court.",
        null=True,
        blank=True,
    )
    de_date_end = models.DateField(
        help_text="Only fetch docket entries (de) older than or equal to this "
        "date. Timezone appears to be that of the court.",
        null=True,
        blank=True,
    )
    de_number_start = models.IntegerField(
        help_text="Only fetch docket entries (de) >= than this value. "
        "Warning: Using this parameter will not return numberless "
        "entries.",
        null=True,
        blank=True,
    )
    de_number_end = models.IntegerField(
        help_text="Only fetch docket entries (de) <= this value. "
        "Warning: Using this parameter will not return numberless "
        "entries.",
        null=True,
        blank=True,
    )
    show_parties_and_counsel = models.BooleanField(
        help_text="Should we pull parties and counsel for a docket report?",
        default=True,
    )
    show_terminated_parties = models.BooleanField(
        help_text="Should we pull terminated parties and counsel as well?",
        default=True,
    )
    show_list_of_member_cases = models.BooleanField(
        help_text="Should we pull the list of member cases? This can add "
        "considerable expense to each docket.",
        default=False,
    )

    def __str__(self) -> str:
        return f"{self.pk} ({self.get_request_type_display()})"


class FjcIntegratedDatabase(AbstractDateTimeModel):
    """The Integrated Database of PACER data as described here:

    https://www.fjc.gov/research/idb

    Most fields are simply copied across as chars, though some are normalized
    if possible.
    """

    ORIG = 1
    REMOVED = 2
    REMANDED = 3
    REINSTATED = 4
    TRANSFERRED = 5
    MULTI_DIST = 6
    APPEAL_FROM_MAG = 7
    SECOND_REOPEN = 8
    THIRD_REOPEN = 9
    FOURTH_REOPEN = 10
    FIFTH_REOPEN = 11
    SIXTH_REOPEN = 12
    MULTI_DIST_ORIG = 13
    ORIGINS = (
        (ORIG, "Original Proceeding"),
        (
            REMOVED,
            "Removed  (began in the state court, removed to the "
            "district court)",
        ),
        (
            REMANDED,
            "Remanded for further action (removal from court of appeals)",
        ),
        (
            REINSTATED,
            "Reinstated/reopened (previously opened and closed, "
            "reopened for additional action)",
        ),
        (
            TRANSFERRED,
            "Transferred from another district(pursuant to 28 USC 1404)",
        ),
        (
            MULTI_DIST,
            "Multi district litigation (cases transferred to this "
            "district by an order entered by Judicial Panel on Multi "
            "District Litigation pursuant to 28 USC 1407)",
        ),
        (
            APPEAL_FROM_MAG,
            "Appeal to a district judge of a magistrate judge's decision",
        ),
        (SECOND_REOPEN, "Second reopen"),
        (THIRD_REOPEN, "Third reopen"),
        (FOURTH_REOPEN, "Fourth reopen"),
        (FIFTH_REOPEN, "Fifth reopen"),
        (SIXTH_REOPEN, "Sixth reopen"),
        (
            MULTI_DIST_ORIG,
            "Multi district litigation originating in the "
            "district (valid beginning July 1, 2016)",
        ),
    )
    GOV_PLAIN = 1
    GOV_DEF = 2
    FED_Q = 3
    DIV_OF_CITZ = 4
    LOCAL_Q = 5
    JURISDICTIONS = (
        (GOV_PLAIN, "Government plaintiff"),
        (GOV_DEF, "Government defendant"),
        (FED_Q, "Federal question"),
        (DIV_OF_CITZ, "Diversity of citizenship"),
        (LOCAL_Q, "Local question"),
    )
    MANDATORY = "M"
    VOLUNTARY = "V"
    EXEMPT = "E"
    YES = "Y"
    ARBITRATION_CHOICES = (
        (MANDATORY, "Mandatory"),
        (VOLUNTARY, "Voluntary"),
        (EXEMPT, "Exempt"),
        (YES, "Yes, but type unknown"),
    )
    CLASS_ACTION_DENIED = 2
    CLASS_ACTION_GRANTED = 3
    CLASS_ACTION_STATUSES = (
        (CLASS_ACTION_DENIED, "Denied"),
        (CLASS_ACTION_GRANTED, "Granted"),
    )
    NO_COURT_ACTION_PRE_ISSUE_JOINED = 1
    ORDER_ENTERED = 2
    HEARING_HELD = 11
    ORDER_DECIDED = 12
    NO_COURT_ACTION_POST_ISSUE_JOINED = 3
    JUDGMENT_ON_MOTION = 4
    PRETRIAL_CONFERENCE_HELD = 5
    DURING_COURT_TRIAL = 6
    DURING_JURY_TRIAL = 7
    AFTER_COURT_TRIAL = 8
    AFTER_JURY_TRIAL = 9
    OTHER_PROCEDURAL_PROGRESS = 10
    REQUEST_FOR_DE_NOVO = 13
    PROCEDURAL_PROGRESSES = (
        (
            "Before issue joined",
            (
                (
                    NO_COURT_ACTION_PRE_ISSUE_JOINED,
                    "No court action (before issue joined)",
                ),
                (ORDER_ENTERED, "Order entered"),
                (HEARING_HELD, "Hearing held"),
                (ORDER_DECIDED, "Order decided"),
            ),
        ),
        (
            "After issue joined",
            (
                (
                    NO_COURT_ACTION_POST_ISSUE_JOINED,
                    "No court action (after issue joined)",
                ),
                (JUDGMENT_ON_MOTION, "Judgment on motion"),
                (PRETRIAL_CONFERENCE_HELD, "Pretrial conference held"),
                (DURING_COURT_TRIAL, "During court trial"),
                (DURING_JURY_TRIAL, "During jury trial"),
                (AFTER_COURT_TRIAL, "After court trial"),
                (AFTER_JURY_TRIAL, "After jury trial"),
                (OTHER_PROCEDURAL_PROGRESS, "Other"),
                (
                    REQUEST_FOR_DE_NOVO,
                    "Request for trial de novo after arbitration",
                ),
            ),
        ),
    )
    TRANSFER_TO_DISTRICT = 0
    REMANDED_TO_STATE = 1
    TRANSFER_TO_MULTI = 10
    REMANDED_TO_AGENCY = 11
    WANT_OF_PROSECUTION = 2
    LACK_OF_JURISDICTION = 3
    VOLUNTARILY_DISMISSED = 12
    SETTLED = 13
    OTHER_DISMISSAL = 14
    DEFAULT = 4
    CONSENT = 5
    MOTION_BEFORE_TRIAL = 6
    JURY_VERDICT = 7
    DIRECTED_VERDICT = 8
    COURT_TRIAL = 9
    AWARD_OF_ARBITRATOR = 15
    STAYED_PENDING_BANKR = 16
    OTHER_DISPOSITION = 17
    STATISTICAL_CLOSING = 18
    APPEAL_AFFIRMED = 19
    APPEAL_DENIED = 20
    DISPOSITIONS = (
        (
            "Cases transferred or remanded",
            (
                (TRANSFER_TO_DISTRICT, "Transfer to another district"),
                (REMANDED_TO_STATE, "Remanded to state court"),
                (TRANSFER_TO_MULTI, "Multi-district litigation transfer"),
                (REMANDED_TO_AGENCY, "Remanded to U.S. agency"),
            ),
        ),
        (
            "Dismissals",
            (
                (WANT_OF_PROSECUTION, "Want of prosecution"),
                (LACK_OF_JURISDICTION, "Lack of jurisdiction"),
                (VOLUNTARILY_DISMISSED, "Voluntarily dismissed"),
                (SETTLED, "Settled"),
                (OTHER_DISMISSAL, "Other"),
            ),
        ),
        (
            "Judgment on",
            (
                (DEFAULT, "Default"),
                (CONSENT, "Consent"),
                (MOTION_BEFORE_TRIAL, "Motion before trial"),
                (JURY_VERDICT, "Jury verdict"),
                (DIRECTED_VERDICT, "Directed verdict"),
                (COURT_TRIAL, "Court trial"),
                (AWARD_OF_ARBITRATOR, "Award of arbitrator"),
                (STAYED_PENDING_BANKR, "Stayed pending bankruptcy"),
                (OTHER_DISPOSITION, "Other"),
                (STATISTICAL_CLOSING, "Statistical closing"),
                (APPEAL_AFFIRMED, "Appeal affirmed (magistrate judge)"),
                (APPEAL_DENIED, "Appeal denied (magistrate judge"),
            ),
        ),
    )
    NO_MONEY = 0
    MONEY_ONLY = 1
    MONEY_AND = 2
    INJUNCTION = 3
    FORFEITURE_ETC = 4
    COSTS_ONLY = 5
    COSTS_AND_FEES = 6
    NATURE_OF_JUDGMENT_CODES = (
        (NO_MONEY, "No monetary award"),
        (MONEY_ONLY, "Monetary award only"),
        (MONEY_AND, "Monetary award and other"),
        (INJUNCTION, "Injunction"),
        (FORFEITURE_ETC, "Forfeiture/foreclosure/condemnation, etc."),
        (COSTS_ONLY, "Costs only"),
        (COSTS_AND_FEES, "Costs and attorney fees"),
    )
    PLAINTIFF = 1
    DEFENDANT = 2
    PLAINTIFF_AND_DEFENDANT = 3
    UNKNOWN_FAVORING = 4
    JUDGMENT_FAVORS = (
        (PLAINTIFF, "Plaintiff"),
        (DEFENDANT, "Defendant"),
        (PLAINTIFF_AND_DEFENDANT, "Both plaintiff and defendant"),
        (UNKNOWN_FAVORING, "Unknown"),
    )
    PRO_SE_NONE = 0
    PRO_SE_PLAINTIFFS = 1
    PRO_SE_DEFENDANTS = 2
    PRO_SE_BOTH = 3
    PRO_SE_CHOICES = (
        (PRO_SE_NONE, "No pro se plaintiffs or defendants"),
        (PRO_SE_PLAINTIFFS, "Pro se plaintiffs, but no pro se defendants"),
        (PRO_SE_DEFENDANTS, "Pro se defendants, but no pro se plaintiffs"),
        (PRO_SE_BOTH, "Both pro se plaintiffs & defendants"),
    )
    dataset_source = models.SmallIntegerField(
        help_text="IDB has several source datafiles. This field helps keep "
        "track of where a row came from originally.",
        choices=DATASET_SOURCES,
    )
    circuit = models.ForeignKey(
        Court,
        help_text="Circuit in which the case was filed.",
        related_name="+",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
    )
    district = models.ForeignKey(
        Court,
        help_text="District court in which the case was filed.",
        related_name="idb_cases",
        on_delete=models.RESTRICT,
        db_index=True,
        null=True,
        blank=True,
    )
    office = models.CharField(
        help_text="The code that designates the office within the district "
        "where the case is filed. Must conform with format "
        "established in Volume XI, Guide to Judiciary Policies and "
        "Procedures, Appendix A. See: https://free.law/idb-facts/",
        max_length=3,
        blank=True,
    )
    docket_number = models.CharField(
        # use a char field here because we need preceding zeros.
        help_text="The number assigned by the Clerks' office; consists of 2 "
        "digit Docket Year (usually calendar year in which the case "
        "was filed) and 5 digit sequence number.",
        blank=True,
        max_length=7,
    )
    origin = models.SmallIntegerField(
        help_text="A single digit code describing the manner in which the "
        "case was filed in the district.",
        choices=ORIGINS,
        blank=True,
        null=True,
    )
    date_filed = models.DateField(
        help_text="The date on which the case was filed in the district.",
        db_index=True,
        null=True,
        blank=True,
    )
    jurisdiction = models.SmallIntegerField(
        help_text="The code which provides the basis for the U.S. district "
        "court jurisdiction in the case. This code is used in "
        "conjunction with appropriate nature of suit code.",
        choices=JURISDICTIONS,
        blank=True,
        null=True,
    )
    nature_of_suit = models.IntegerField(
        help_text="A three digit statistical code representing the nature of "
        "suit of the action filed.",
        choices=NOS_CODES,
        blank=True,
        null=True,
    )
    # Via email from FJC, title and section fields are alternative for "cause"
    # field.
    title = models.TextField(
        help_text="No description provided by FJC.",
        blank=True,
        db_index=True,
    )
    section = models.CharField(
        help_text="No description provided by FJC.",
        max_length=200,
        db_index=True,
        blank=True,
    )
    subsection = models.CharField(
        help_text="No description provided by FJC.",
        max_length=200,
        db_index=True,
        blank=True,
    )
    diversity_of_residence = models.SmallIntegerField(
        help_text="Involves diversity of citizenship for the plaintiff and "
        "defendant. First position is the citizenship of the "
        "plaintiff, second position is the citizenship of the "
        "defendant. Only used when jurisdiction is 4",
        blank=True,
        null=True,
    )
    class_action = models.BooleanField(
        help_text="Involves an allegation by the plaintiff that the complaint "
        'meets the prerequisites of a "Class Action" as provided '
        "in Rule 23 - F.R.CV.P. ",
        null=True,
    )
    monetary_demand = models.IntegerField(
        help_text="The monetary amount sought by plaintiff (in thousands). "
        "Amounts less than $500 appear as 1, and amounts over $10k "
        "appear as 9999. See notes in codebook.",
        null=True,
        blank=True,
    )
    county_of_residence = models.IntegerField(
        help_text="The code for the county of residence of the first listed "
        "plaintiff (see notes in codebook). Appears to use FIPS "
        "code.",
        null=True,
        blank=True,
    )
    arbitration_at_filing = models.CharField(
        help_text="This field is used only by the courts  participating in "
        "the Formal Arbitration Program.  It is not used for any "
        "other purpose.",
        max_length=1,
        choices=ARBITRATION_CHOICES,
        blank=True,
    )
    arbitration_at_termination = models.CharField(
        help_text="Termination arbitration code.",
        max_length=1,
        choices=ARBITRATION_CHOICES,
        blank=True,
    )
    multidistrict_litigation_docket_number = models.TextField(
        help_text="A 4 digit multi district litigation docket number.",
        blank=True,
    )
    plaintiff = models.TextField(
        help_text="First listed plaintiff. This field appears to be cut off "
        "at 30 characters",
        db_index=True,
        blank=True,
    )
    defendant = models.TextField(
        help_text="First listed defendant. This field appears to be cut off "
        "at 30 characters.",
        db_index=True,
        blank=True,
    )
    date_transfer = models.DateField(
        help_text="The date when the papers were received in the receiving "
        "district for a transferred  case.",
        blank=True,
        null=True,
    )
    transfer_office = models.CharField(
        help_text="The office number of the district losing the case.",
        max_length=3,
        blank=True,
    )
    transfer_docket_number = models.TextField(
        help_text="The docket number of the case in the losing district",
        blank=True,
    )
    transfer_origin = models.TextField(
        help_text="The origin number of the case in the losing district",
        blank=True,
    )
    date_terminated = models.DateField(
        help_text="The date the district court received the final judgment or "
        "the order disposing of the case.",
        null=True,
        blank=True,
    )
    termination_class_action_status = models.SmallIntegerField(
        help_text="A code that indicates a case involving allegations of "
        "class action.",
        choices=CLASS_ACTION_STATUSES,
        null=True,
        blank=True,
    )
    procedural_progress = models.SmallIntegerField(
        help_text="The point to which the case had progressed when it was "
        "disposed of. See notes in codebook.",
        choices=PROCEDURAL_PROGRESSES,
        null=True,
        blank=True,
    )
    disposition = models.SmallIntegerField(
        help_text="The manner in which the case was disposed of.",
        choices=DISPOSITIONS,
        null=True,
        blank=True,
    )
    nature_of_judgement = models.SmallIntegerField(
        help_text="Cases disposed of by an entry of a final judgment.",
        choices=NATURE_OF_JUDGMENT_CODES,
        null=True,
        blank=True,
    )
    amount_received = models.IntegerField(
        help_text="Dollar amount received (in thousands) when appropriate. "
        "Field not used uniformally; see codebook.",
        null=True,
        blank=True,
    )
    judgment = models.SmallIntegerField(
        help_text="Which party the cases was disposed in favor of.",
        choices=JUDGMENT_FAVORS,
        null=True,
        blank=True,
    )
    pro_se = models.SmallIntegerField(
        help_text="Which parties filed pro se? (See codebook for more "
        "details.)",
        choices=PRO_SE_CHOICES,
        null=True,
        blank=True,
    )
    year_of_tape = models.IntegerField(
        help_text="Statistical year label on data files obtained from the "
        "Administrative Office of the United States Courts.  2099 "
        "on pending case records.",
        blank=True,
        null=True,
    )

    # Criminal fields
    nature_of_offense = models.CharField(
        help_text="The four digit D2 offense code associated with the filing "
        "title/secion 1. These codes were created in FY2005 to "
        "replace the AO offense codes.",
        max_length=4,
        choices=NOO_CODES,
        blank=True,
    )
    version = models.IntegerField(
        help_text="This field was created in FY 2012. It increments with each "
        "update received to a defendant record.",
        null=True,
        blank=True,
    )

    def __str__(self) -> str:
        return f"{self.pk}: {self.plaintiff} v. {self.defendant}"

    class Meta:
        verbose_name_plural = "FJC Integrated Database Entries"
        indexes = [models.Index(fields=["district", "docket_number"])]
