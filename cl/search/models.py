import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Tuple, TypeVar

import pghistory
import pytz
from asgiref.sync import sync_to_async
from celery.canvas import chain
from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.postgres.indexes import HashIndex
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.db.models import Q, QuerySet
from django.db.models.functions import MD5
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.encoding import force_str
from django.utils.functional import cached_property
from django.utils.text import slugify
from eyecite import get_citations
from eyecite.tokenizers import HyperscanTokenizer
from localflavor.us.models import USPostalCodeField, USZipCodeField
from localflavor.us.us_states import OBSOLETE_STATES, USPS_CHOICES
from model_utils import FieldTracker

from cl.citations.utils import get_citation_depth_between_clusters
from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.lib import fields
from cl.lib.date_time import midnight_pt
from cl.lib.model_helpers import (
    CSVExportMixin,
    linkify_orig_docket_number,
    make_docket_number_core,
    make_recap_path,
    make_upload_path,
)
from cl.lib.models import AbstractDateTimeModel, AbstractPDF, s3_warning_note
from cl.lib.search_index_utils import InvalidDocumentError
from cl.lib.storage import IncrementingAWSMediaStorage
from cl.lib.string_utils import trunc
from cl.search.docket_sources import DocketSources
from cl.users.models import User

HYPERSCAN_TOKENIZER = HyperscanTokenizer(cache_dir=".hyperscan")

logger = logging.getLogger(__name__)


class PRECEDENTIAL_STATUS:
    PUBLISHED = "Published"
    UNPUBLISHED = "Unpublished"
    ERRATA = "Errata"
    SEPARATE = "Separate"
    IN_CHAMBERS = "In-chambers"
    RELATING_TO = "Relating-to"
    UNKNOWN = "Unknown"

    NAMES = (
        (PUBLISHED, "Precedential"),
        (UNPUBLISHED, "Non-Precedential"),
        (ERRATA, "Errata"),
        (SEPARATE, "Separate Opinion"),
        (IN_CHAMBERS, "In-chambers"),
        (RELATING_TO, "Relating-to orders"),
        (UNKNOWN, "Unknown Status"),
    )

    @classmethod
    def get_status_value(cls, name):
        reverse_names = {value: key for key, value in cls.NAMES}
        return reverse_names.get(name)

    @classmethod
    def get_status_value_reverse(cls, name):
        reverse_names = {key: value for key, value in cls.NAMES}
        return reverse_names.get(name)


class SOURCES:
    COURT_WEBSITE = "C"
    PUBLIC_RESOURCE = "R"
    COURT_M_RESOURCE = "CR"
    LAWBOX = "L"
    LAWBOX_M_COURT = "LC"
    LAWBOX_M_RESOURCE = "LR"
    LAWBOX_M_COURT_RESOURCE = "LCR"
    MANUAL_INPUT = "M"
    INTERNET_ARCHIVE = "A"
    BRAD_HEATH_ARCHIVE = "H"
    COLUMBIA_ARCHIVE = "Z"
    HARVARD_CASELAW = "U"
    COURT_M_HARVARD = "CU"
    DIRECT_COURT_INPUT = "D"
    ANON_2020 = "Q"
    ANON_2020_M_HARVARD = "QU"
    COURT_M_RESOURCE_M_HARVARD = "CRU"
    DIRECT_COURT_INPUT_M_HARVARD = "DU"
    LAWBOX_M_HARVARD = "LU"
    LAWBOX_M_COURT_M_HARVARD = "LCU"
    LAWBOX_M_RESOURCE_M_HARVARD = "LRU"
    LAWBOX_M_COURT_RESOURCE_M_HARVARD = "LCRU"
    MANUAL_INPUT_M_HARVARD = "MU"
    PUBLIC_RESOURCE_M_HARVARD = "RU"
    COLUMBIA_M_INTERNET_ARCHIVE = "ZA"
    COLUMBIA_M_DIRECT_COURT_INPUT = "ZD"
    COLUMBIA_M_COURT = "ZC"
    COLUMBIA_M_BRAD_HEATH_ARCHIVE = "ZH"
    COLUMBIA_M_LAWBOX_COURT = "ZLC"
    COLUMBIA_M_LAWBOX_RESOURCE = "ZLR"
    COLUMBIA_M_LAWBOX_COURT_RESOURCE = "ZLCR"
    COLUMBIA_M_RESOURCE = "ZR"
    COLUMBIA_M_COURT_RESOURCE = "ZCR"
    COLUMBIA_M_LAWBOX = "ZL"
    COLUMBIA_M_MANUAL = "ZM"
    COLUMBIA_M_ANON_2020 = "ZQ"
    COLUMBIA_ARCHIVE_M_HARVARD = "ZU"
    COLUMBIA_M_LAWBOX_M_HARVARD = "ZLU"
    COLUMBIA_M_DIRECT_COURT_INPUT_M_HARVARD = "ZDU"
    COLUMBIA_M_LAWBOX_M_RESOURCE_M_HARVARD = "ZLRU"
    COLUMBIA_M_LAWBOX_M_COURT_RESOURCE_M_HARVARD = "ZLCRU"
    COLUMBIA_M_COURT_M_HARVARD = "ZCU"
    COLUMBIA_M_MANUAL_INPUT_M_HARVARD = "ZMU"
    COLUMBIA_M_PUBLIC_RESOURCE_M_HARVARD = "ZRU"
    COLUMBIA_M_LAWBOX_M_COURT_M_HARVARD = "ZLCU"
    RECAP = "G"
    NAMES = (
        (COURT_WEBSITE, "court website"),
        (PUBLIC_RESOURCE, "public.resource.org"),
        (COURT_M_RESOURCE, "court website merged with resource.org"),
        (LAWBOX, "lawbox"),
        (LAWBOX_M_COURT, "lawbox merged with court"),
        (LAWBOX_M_RESOURCE, "lawbox merged with resource.org"),
        (LAWBOX_M_COURT_RESOURCE, "lawbox merged with court and resource.org"),
        (MANUAL_INPUT, "manual input"),
        (INTERNET_ARCHIVE, "internet archive"),
        (BRAD_HEATH_ARCHIVE, "brad heath archive"),
        (COLUMBIA_ARCHIVE, "columbia archive"),
        (COLUMBIA_M_INTERNET_ARCHIVE, "columbia merged with internet archive"),
        (
            COLUMBIA_M_DIRECT_COURT_INPUT,
            "columbia merged with direct court input",
        ),
        (COLUMBIA_M_COURT, "columbia merged with court"),
        (
            COLUMBIA_M_BRAD_HEATH_ARCHIVE,
            "columbia merged with brad heath archive",
        ),
        (COLUMBIA_M_LAWBOX_COURT, "columbia merged with lawbox and court"),
        (
            COLUMBIA_M_LAWBOX_RESOURCE,
            "columbia merged with lawbox and resource.org",
        ),
        (
            COLUMBIA_M_LAWBOX_COURT_RESOURCE,
            "columbia merged with lawbox, court, and resource.org",
        ),
        (COLUMBIA_M_RESOURCE, "columbia merged with resource.org"),
        (
            COLUMBIA_M_COURT_RESOURCE,
            "columbia merged with court and resource.org",
        ),
        (COLUMBIA_M_LAWBOX, "columbia merged with lawbox"),
        (COLUMBIA_M_MANUAL, "columbia merged with manual input"),
        (COLUMBIA_M_ANON_2020, "columbia merged with 2020 anonymous database"),
        (
            HARVARD_CASELAW,
            "Harvard, Library Innovation Lab Case Law Access Project",
        ),
        (COURT_M_HARVARD, "court website merged with Harvard"),
        (DIRECT_COURT_INPUT, "direct court input"),
        (ANON_2020, "2020 anonymous database"),
        (ANON_2020_M_HARVARD, "2020 anonymous database merged with Harvard"),
        (COURT_M_HARVARD, "court website merged with Harvard"),
        (
            COURT_M_RESOURCE_M_HARVARD,
            "court website merged with public.resource.org and Harvard",
        ),
        (
            DIRECT_COURT_INPUT_M_HARVARD,
            "direct court input merged with Harvard",
        ),
        (LAWBOX_M_HARVARD, "lawbox merged with Harvard"),
        (
            LAWBOX_M_COURT_M_HARVARD,
            "Lawbox merged with court website and Harvard",
        ),
        (
            LAWBOX_M_RESOURCE_M_HARVARD,
            "Lawbox merged with public.resource.org and with Harvard",
        ),
        (MANUAL_INPUT_M_HARVARD, "Manual input merged with Harvard"),
        (PUBLIC_RESOURCE_M_HARVARD, "public.resource.org merged with Harvard"),
        (COLUMBIA_ARCHIVE_M_HARVARD, "columbia archive merged with Harvard"),
        (
            COLUMBIA_M_LAWBOX_M_HARVARD,
            "columbia archive merged with Lawbox and Harvard",
        ),
        (
            COLUMBIA_M_DIRECT_COURT_INPUT_M_HARVARD,
            "columbia archive merged with direct court input and Harvard",
        ),
        (
            COLUMBIA_M_LAWBOX_M_RESOURCE_M_HARVARD,
            "columbia archive merged with lawbox, public.resource.org and Harvard",
        ),
        (
            COLUMBIA_M_LAWBOX_M_COURT_RESOURCE_M_HARVARD,
            "columbia archive merged with lawbox, court website, public.resource.org and Harvard",
        ),
        (
            COLUMBIA_M_COURT_M_HARVARD,
            "columbia archive merged with court website and Harvard",
        ),
        (
            COLUMBIA_M_MANUAL_INPUT_M_HARVARD,
            "columbia archive merged with manual input and Harvard",
        ),
        (
            COLUMBIA_M_PUBLIC_RESOURCE_M_HARVARD,
            "columbia archive merged with public.resource.org and Harvard",
        ),
        (
            COLUMBIA_M_LAWBOX_M_COURT_M_HARVARD,
            "columbia archive merged with lawbox, court website and Harvard",
        ),
        (
            RECAP,
            "recap",
        ),
    )


@pghistory.track()
class OriginatingCourtInformation(AbstractDateTimeModel):
    """Lower court metadata to associate with appellate cases.

    For example, if you appeal from a district court to a circuit court, the
    district court information would be in here. You may wonder, "Why do we
    duplicate this information?" Well:

        1. We don't want to update the lower court case based on information
           we learn in the upper court. Say they have a conflict? Which do we
           trust?

        2. We may have the docket from the upper court without ever getting
           docket information for the lower court. If that happens, would we
           create a docket for the lower court using only the info in the
           upper court. That seems bad.

    The other thought you might have is, "Why not just associate this directly
    with the docket object —-- why do we have a 1to1 join between them?" This
    was a difficult data modelling decision. There are a few answers:

        1. Most cases in the RECAP Archive are not appellate cases. For those
           cases, the extra fields for this information would just pollute the
           Docket namespace.

        2. In general, we prefer to have Docket.originating_court_data.field
           than, Docket.ogc_field.
    """

    docket_number = models.TextField(
        help_text="The docket number in the lower court.", blank=True
    )
    assigned_to = models.ForeignKey(
        "people_db.Person",
        help_text="The judge the case was assigned to.",
        related_name="original_court_info",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
    )
    assigned_to_str = models.TextField(
        help_text="The judge that the case was assigned to, as a string.",
        blank=True,
    )
    ordering_judge = models.ForeignKey(
        "people_db.Person",
        related_name="+",
        help_text="The judge that issued the final order in the case.",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
    )
    ordering_judge_str = models.TextField(
        help_text=(
            "The judge that issued the final order in the case, as a "
            "string."
        ),
        blank=True,
    )
    court_reporter = models.TextField(
        help_text="The court reporter responsible for the case.", blank=True
    )
    date_disposed = models.DateField(
        help_text="The date the case was disposed at the lower court.",
        blank=True,
        null=True,
    )
    date_filed = models.DateField(
        help_text="The date the case was filed in the lower court.",
        blank=True,
        null=True,
    )
    date_judgment = models.DateField(
        help_text="The date of the order or judgment in the lower court.",
        blank=True,
        null=True,
    )
    date_judgment_eod = models.DateField(
        help_text=(
            "The date the judgment was Entered On the Docket at the "
            "lower court."
        ),
        blank=True,
        null=True,
    )
    date_filed_noa = models.DateField(
        help_text="The date the notice of appeal was filed for the case.",
        blank=True,
        null=True,
    )
    date_received_coa = models.DateField(
        help_text="The date the case was received at the court of appeals.",
        blank=True,
        null=True,
    )

    @property
    def administrative_link(self):
        return linkify_orig_docket_number(
            self.docket.appeal_from_str, self.docket_number
        )

    def get_absolute_url(self) -> str:
        return self.docket.get_absolute_url()

    class Meta:
        verbose_name_plural = "Originating Court Information"


@pghistory.track(
    pghistory.UpdateEvent(
        condition=pghistory.AnyChange(exclude_auto=True), row=pghistory.Old
    ),
    pghistory.DeleteEvent(),
    exclude=["view_count"],
)
class Docket(AbstractDateTimeModel, DocketSources):
    """A class to sit above OpinionClusters, Audio files, and Docket Entries,
    and link them together.
    """

    source = models.SmallIntegerField(
        help_text="contains the source of the Docket.",
        choices=DocketSources.SOURCE_CHOICES,
    )
    court = models.ForeignKey(
        "Court",
        help_text="The court where the docket was filed",
        on_delete=models.RESTRICT,
        db_index=True,
        related_name="dockets",
    )
    appeal_from = models.ForeignKey(
        "Court",
        help_text=(
            "In appellate cases, this is the lower court or "
            "administrative body where this case was originally heard. "
            "This field is frequently blank due to it not being "
            "populated historically or due to our inability to "
            "normalize the value in appeal_from_str."
        ),
        related_name="+",
        on_delete=models.RESTRICT,
        blank=True,
        null=True,
    )
    parent_docket = models.ForeignKey(
        "self",
        help_text="In criminal cases (and some magistrate) PACER creates "
        "a parent docket and one or more child dockets. Child dockets "
        "contain docket information for each individual defendant "
        "while parent dockets are a superset of all docket entries.",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="child_dockets",
    )
    appeal_from_str = models.TextField(
        help_text=(
            "In appellate cases, this is the lower court or "
            "administrative body where this case was originally heard. "
            "This field is frequently blank due to it not being "
            "populated historically. This field may have values when "
            "the appeal_from field does not. That can happen if we are "
            "unable to normalize the value in this field."
        ),
        blank=True,
    )
    originating_court_information = models.OneToOneField(
        OriginatingCourtInformation,
        help_text="Lower court information for appellate dockets",
        related_name="docket",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    idb_data = models.OneToOneField(
        "recap.FjcIntegratedDatabase",
        help_text=(
            "Data from the FJC Integrated Database associated with this "
            "case."
        ),
        related_name="docket",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    tags = models.ManyToManyField(
        "search.Tag",
        help_text="The tags associated with the docket.",
        related_name="dockets",
        blank=True,
    )
    html_documents = GenericRelation(
        "recap.PacerHtmlFiles",
        help_text="Original HTML files collected from PACER.",
        related_query_name="dockets",
        null=True,
        blank=True,
    )
    assigned_to = models.ForeignKey(
        "people_db.Person",
        related_name="assigning",
        help_text="The judge the case was assigned to.",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
    )
    assigned_to_str = models.TextField(
        help_text="The judge that the case was assigned to, as a string.",
        blank=True,
    )
    referred_to = models.ForeignKey(
        "people_db.Person",
        related_name="referring",
        help_text="The judge to whom the 'assigned_to' judge is delegated.",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
    )
    referred_to_str = models.TextField(
        help_text="The judge that the case was referred to, as a string.",
        blank=True,
    )
    panel = models.ManyToManyField(
        "people_db.Person",
        help_text=(
            "The empaneled judges for the case. Currently an unused "
            "field but planned to be used in conjunction with the "
            "panel_str field."
        ),
        related_name="empanelled_dockets",
        blank=True,
    )
    panel_str = models.TextField(
        help_text=(
            "The initials of the judges on the panel that heard this "
            "case. This field is similar to the 'judges' field on "
            "the cluster, but contains initials instead of full judge "
            "names, and applies to the case on the whole instead of "
            "only to a specific decision."
        ),
        blank=True,
    )
    parties = models.ManyToManyField(
        "people_db.Party",
        help_text="The parties involved in the docket",
        related_name="dockets",
        through="people_db.PartyType",
        blank=True,
    )
    date_last_index = models.DateTimeField(
        help_text="The last moment that the item was indexed in Solr.",
        null=True,
        blank=True,
    )
    date_cert_granted = models.DateField(
        help_text="date cert was granted for this case, if applicable",
        blank=True,
        null=True,
    )
    date_cert_denied = models.DateField(
        help_text="the date cert was denied for this case, if applicable",
        blank=True,
        null=True,
    )
    date_argued = models.DateField(
        help_text="the date the case was argued",
        blank=True,
        null=True,
    )
    date_reargued = models.DateField(
        help_text="the date the case was reargued",
        blank=True,
        null=True,
    )
    date_reargument_denied = models.DateField(
        help_text="the date the reargument was denied",
        blank=True,
        null=True,
    )
    date_filed = models.DateField(
        help_text="The date the case was filed.", blank=True, null=True
    )
    date_terminated = models.DateField(
        help_text="The date the case was terminated.", blank=True, null=True
    )
    date_last_filing = models.DateField(
        help_text=(
            "The date the case was last updated in the docket, as shown "
            "in PACER's Docket History report or iquery page."
        ),
        blank=True,
        null=True,
    )
    case_name_short = models.TextField(
        help_text="The abridged name of the case, often a single word, e.g. "
        "'Marsh'",
        blank=True,
    )
    case_name = models.TextField(
        help_text="The standard name of the case", blank=True
    )
    case_name_full = models.TextField(
        help_text="The full name of the case", blank=True
    )
    slug = models.SlugField(
        help_text="URL that the document should map to (the slug)",
        max_length=75,
        db_index=False,
        blank=True,
    )
    docket_number = models.TextField(  # nosemgrep
        help_text="The docket numbers of a case, can be consolidated and "
        "quite long. In some instances they are too long to be "
        "indexed by postgres and we store the full docket in "
        "the correction field on the Opinion Cluster.",
        blank=True,
        null=True,
    )
    docket_number_core = models.CharField(
        help_text=(
            "For federal district court dockets, this is the most "
            "distilled docket number available. In this field, the "
            "docket number is stripped down to only the year and serial "
            "digits, eliminating the office at the beginning, letters "
            "in the middle, and the judge at the end. Thus, a docket "
            "number like 2:07-cv-34911-MJL becomes simply 0734911. This "
            "is the format that is provided by the IDB and is useful "
            "for de-duplication types of activities which otherwise get "
            "messy. We use a char field here to preserve leading zeros."
        ),
        # PACER doesn't do consolidated case numbers, so this can be small.
        max_length=20,
        blank=True,
        db_index=True,
    )
    federal_dn_office_code = models.CharField(
        help_text="A one digit statistical code (either alphabetic or numeric) "
        "of the office within the federal district. In this "
        "example, 2:07-cv-34911-MJL, the 2 preceding "
        "the : is the office code.",
        max_length=3,
        blank=True,
    )
    federal_dn_case_type = models.CharField(
        help_text="Case type, e.g., civil (cv), magistrate (mj), criminal (cr), "
        "petty offense (po), and miscellaneous (mc). These codes "
        "can be upper case or lower case, and may vary in number of "
        "characters.",
        max_length=6,
        blank=True,
    )
    federal_dn_judge_initials_assigned = models.CharField(
        help_text="A typically three-letter upper cased abbreviation "
        "of the judge's initials. In the example 2:07-cv-34911-MJL, "
        "MJL is the judge's initials. Judge initials change if a "
        "new judge takes over a case.",
        max_length=5,
        blank=True,
    )
    federal_dn_judge_initials_referred = models.CharField(
        help_text="A typically three-letter upper cased abbreviation "
        "of the judge's initials. In the example 2:07-cv-34911-MJL-GOG, "
        "GOG is the magistrate judge initials.",
        max_length=5,
        blank=True,
    )
    federal_defendant_number = models.SmallIntegerField(
        help_text="A unique number assigned to each defendant in a case, "
        "typically found in pacer criminal cases as a -1, -2 after "
        "the judge initials. Example: 1:14-cr-10363-RGS-1.",
        null=True,
        blank=True,
    )
    # Nullable for unique constraint requirements.
    pacer_case_id = fields.CharNullField(
        help_text="The case ID provided by PACER.",
        max_length=100,
        blank=True,
        null=True,
        db_index=True,
    )
    cause = models.CharField(
        help_text="The cause for the case.",
        max_length=2000,  # Was 200, 500, 1000
        blank=True,
    )
    nature_of_suit = models.CharField(
        help_text="The nature of suit code from PACER.",
        max_length=1000,  # Was 100, 500
        blank=True,
    )
    jury_demand = models.CharField(
        help_text="The compensation demand.", max_length=500, blank=True
    )
    jurisdiction_type = models.CharField(
        help_text=(
            "Stands for jurisdiction in RECAP XML docket. For example, "
            "'Diversity', 'U.S. Government Defendant'."
        ),
        max_length=100,
        blank=True,
    )
    appellate_fee_status = models.TextField(
        help_text=(
            "The status of the fee in the appellate court. Can be used "
            "as a hint as to whether the government is the appellant "
            "(in which case the fee is waived)."
        ),
        blank=True,
    )
    appellate_case_type_information = models.TextField(
        help_text=(
            "Information about a case from the appellate docket in "
            "PACER. For example, 'civil, private, bankruptcy'."
        ),
        blank=True,
    )
    mdl_status = models.CharField(
        help_text="The MDL status of a case before the Judicial Panel for "
        "Multidistrict Litigation",
        max_length=100,
        blank=True,
    )
    filepath_local = models.FileField(
        help_text="Path to RECAP's Docket XML page as provided by the "
        "original RECAP architecture. These fields are for backup purposes "
        f"only. {s3_warning_note}",
        upload_to=make_recap_path,
        storage=IncrementingAWSMediaStorage(),
        max_length=1000,
        blank=True,
    )
    filepath_ia = models.CharField(
        help_text="Path to the Docket XML page in The Internet Archive",
        max_length=1000,
        blank=True,
    )
    filepath_ia_json = models.CharField(
        help_text="Path to the docket JSON page in the Internet Archive",
        max_length=1000,
        blank=True,
    )
    ia_upload_failure_count = models.SmallIntegerField(
        help_text="Number of times the upload to the Internet Archive failed.",
        null=True,
        blank=True,
    )
    ia_needs_upload = models.BooleanField(
        help_text=(
            "Does this item need to be uploaded to the Internet "
            "Archive? I.e., has it changed? This field is important "
            "because it keeps track of the status of all the related "
            "objects to the docket. For example, if a related docket "
            "entry changes, we need to upload the item to IA, but we "
            "can't easily check that."
        ),
        blank=True,
        null=True,
    )
    ia_date_first_change = models.DateTimeField(
        help_text=(
            "The moment when this item first changed and was marked as "
            "needing an upload. Used for determining when to upload an "
            "item."
        ),
        null=True,
        blank=True,
    )
    view_count = models.IntegerField(
        help_text="The number of times the docket has been seen.", default=0
    )
    date_blocked = models.DateField(
        help_text=(
            "The date that this opinion was blocked from indexing by "
            "search engines"
        ),
        blank=True,
        null=True,
        db_index=True,
    )
    blocked = models.BooleanField(
        help_text=(
            "Whether a document should be blocked from indexing by "
            "search engines"
        ),
        default=False,
    )
    es_pa_field_tracker = FieldTracker(fields=["docket_number", "court_id"])
    es_oa_field_tracker = FieldTracker(
        fields=[
            "date_argued",
            "date_reargued",
            "date_reargument_denied",
            "docket_number",
            "slug",
        ]
    )
    es_rd_field_tracker = FieldTracker(
        fields=[
            "docket_number",
            "case_name",
            "case_name_short",
            "case_name_full",
            "nature_of_suit",
            "cause",
            "jury_demand",
            "jurisdiction_type",
            "date_argued",
            "date_filed",
            "date_terminated",
            "assigned_to_id",
            "assigned_to_str",
            "referred_to_id",
            "referred_to_str",
            "slug",
            "pacer_case_id",
            "source",
        ]
    )
    es_o_field_tracker = FieldTracker(
        fields=[
            "court_id",
            "docket_number",
            "date_argued",
            "date_reargued",
            "date_reargument_denied",
        ]
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                MD5("docket_number"),
                "pacer_case_id",
                "court_id",
                name="unique_docket_per_court",
            ),
        ]
        indexes = [
            models.Index(fields=["court_id", "id"]),
            models.Index(
                fields=["court_id", "docket_number_core", "pacer_case_id"],
                name="district_court_docket_lookup_idx",
            ),
            HashIndex("docket_number", name="hash_docket_number_lookup_idx"),
        ]

    def __str__(self) -> str:
        if self.case_name:
            return force_str(f"{self.pk}: {self.case_name}")
        else:
            return f"{self.pk}"

    def save(self, update_fields=None, *args, **kwargs):
        self.slug = slugify(trunc(best_case_name(self), 75))
        if self.docket_number and not self.docket_number_core:
            self.docket_number_core = make_docket_number_core(
                self.docket_number
            )

        if self.source in self.RECAP_SOURCES():
            for field in ["pacer_case_id", "docket_number"]:
                if (
                    field == "pacer_case_id"
                    and getattr(self, "court", None)
                    and self.court.jurisdiction == Court.FEDERAL_APPELLATE
                ):
                    continue
                if not getattr(self, field, None):
                    raise ValidationError(
                        f"'{field}' cannot be Null or empty in RECAP dockets."
                    )

        if update_fields is not None:
            update_fields = {"slug", "docket_number_core"}.union(update_fields)

        try:
            # Without a transaction wrapper, a failure will invalidate outer transactions
            with transaction.atomic():
                super().save(update_fields=update_fields, *args, **kwargs)
        except IntegrityError:
            # Temporary patch while we solve #3359
            # If the error is not related to `date_modified` it will raise again
            self.date_modified = timezone.now()
            super().save(update_fields=update_fields, *args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("view_docket", args=[self.pk, self.slug])

    def add_recap_source(self):
        if self.source == self.DEFAULT:
            self.source = self.RECAP_AND_SCRAPER
        elif self.source in self.NON_RECAP_SOURCES():
            # Simply add the RECAP value to the other value.
            self.source = self.source + self.RECAP

    def add_opinions_source(self, scraper_source: int):
        match scraper_source:
            case self.COLUMBIA:
                non_source_list = self.NON_COLUMBIA_SOURCES()
            case self.SCRAPER:
                non_source_list = self.NON_SCRAPER_SOURCES()
            case self.HARVARD:
                non_source_list = self.NON_HARVARD_SOURCES()
            case _:
                return

        if self.source in non_source_list:
            # Simply add the new source value to the other value.
            self.source = self.source + scraper_source

    @property
    def authorities(self):
        """Returns a queryset that can be used for querying and caching
        authorities.
        """
        return OpinionsCitedByRECAPDocument.objects.filter(
            citing_document__docket_entry__docket_id=self.pk
        )

    async def ahas_authorities(self):
        return await self.authorities.aexists()

    @property
    def authority_count(self):
        return self.authorities.count()

    @property
    def authorities_with_data(self):
        """Returns a queryset of this document's authorities for
        eventual injection into a view template.

        The returned queryset is sorted by the depth field.
        """
        return build_authorities_query(self.authorities)

    def add_idb_source(self):
        if self.source in self.NON_IDB_SOURCES():
            self.source = self.source + self.IDB

    def add_anon_2020_source(self) -> None:
        if self.source in self.NON_ANON_2020_SOURCES():
            self.source = self.source + self.ANON_2020

    @property
    def pacer_court_id(self):
        if hasattr(self, "_pacer_court_id"):
            return self._pacer_court_id

        from cl.lib.pacer import map_cl_to_pacer_id

        pacer_court_id = map_cl_to_pacer_id(self.court.pk)
        self._pacer_court_id = pacer_court_id
        return pacer_court_id

    def pacer_district_url(self, path):
        if not self.pacer_case_id or (
            self.court.jurisdiction == Court.FEDERAL_APPELLATE
        ):
            return None
        return f"https://ecf.{self.pacer_court_id}.uscourts.gov/cgi-bin/{path}?{self.pacer_case_id}"

    def pacer_appellate_url_with_caseId(self, path):
        return (
            f"https://ecf.{self.pacer_court_id}.uscourts.gov"
            f"{path}"
            "servlet=CaseSummary.jsp&"
            f"caseId={self.pacer_case_id}&"
            "incOrigDkt=Y&"
            "incDktEntries=Y"
        )

    def pacer_appellate_url_with_caseNum(self, path):
        return (
            f"https://ecf.{self.pacer_court_id}.uscourts.gov"
            f"{path}"
            "servlet=CaseSummary.jsp&"
            f"caseNum={self.docket_number}&"
            "incOrigDkt=Y&"
            "incDktEntries=Y"
        )

    def pacer_acms_url(self):
        return (
            f"https://{self.pacer_court_id}-showdoc.azurewebsites.us/"
            f"{self.docket_number}"
        )

    @property
    def pacer_docket_url(self):
        if self.court.jurisdiction == Court.FEDERAL_APPELLATE:
            if self.court.pk in ["ca5", "ca7", "ca11"]:
                path = "/cmecf/servlet/TransportRoom?"
            else:
                path = "/n/beam/servlet/TransportRoom?"

            if not self.pacer_case_id:
                return self.pacer_appellate_url_with_caseNum(path)
            elif self.pacer_case_id.count("-") > 1:
                return self.pacer_acms_url()
            else:
                return self.pacer_appellate_url_with_caseId(path)
        else:
            return self.pacer_district_url("DktRpt.pl")

    @property
    def pacer_alias_url(self):
        return self.pacer_district_url("qryAlias.pl")

    @property
    def pacer_associated_cases_url(self):
        return self.pacer_district_url("qryAscCases.pl")

    @property
    def pacer_attorney_url(self):
        return self.pacer_district_url("qryAttorneys.pl")

    @property
    def pacer_case_file_location_url(self):
        return self.pacer_district_url("QryRMSLocation.pl")

    @property
    def pacer_summary_url(self):
        return self.pacer_district_url("qrySummary.pl")

    @property
    def pacer_deadlines_and_hearings_url(self):
        return self.pacer_district_url("SchedQry.pl")

    @property
    def pacer_filers_url(self):
        return self.pacer_district_url("FilerQry.pl")

    @property
    def pacer_history_and_documents_url(self):
        return self.pacer_district_url("HistDocQry.pl")

    @property
    def pacer_party_url(self):
        return self.pacer_district_url("qryParties.pl")

    @property
    def pacer_related_transactions_url(self):
        return self.pacer_district_url("RelTransactQry.pl")

    @property
    def pacer_status_url(self):
        return self.pacer_district_url("StatusQry.pl")

    @property
    def pacer_view_doc_url(self):
        return self.pacer_district_url("qryDocument.pl")

    def reprocess_recap_content(self, do_original_xml: bool = False) -> None:
        """Go over any associated RECAP files and reprocess them.

        Start with the XML, then do them in the order they were received since
        that should correspond to the history of the docket itself.

        :param do_original_xml: Whether to do the original XML file as received
        from Internet Archive.
        """
        if self.source not in self.RECAP_SOURCES():
            return

        from cl.lib.pacer import process_docket_data

        # Start with the XML if we've got it.
        if do_original_xml and self.filepath_local:
            from cl.recap.models import UPLOAD_TYPE

            process_docket_data(self, UPLOAD_TYPE.IA_XML_FILE)

        # Then layer the uploads on top of that.
        for html in self.html_documents.order_by("date_created"):
            process_docket_data(
                self, html.upload_type, filepath=html.filepath.path
            )


@pghistory.track(
    pghistory.InsertEvent(), pghistory.DeleteEvent(), obj_field=None
)
class DocketTags(Docket.tags.through):
    """A model class to track docket tags m2m relation"""

    class Meta:
        proxy = True


@pghistory.track(
    pghistory.InsertEvent(), pghistory.DeleteEvent(), obj_field=None
)
class DocketPanel(Docket.panel.through):
    """A model class to track docket panel m2m relation"""

    class Meta:
        proxy = True


@pghistory.track()
class DocketEntry(AbstractDateTimeModel, CSVExportMixin):
    docket = models.ForeignKey(
        Docket,
        help_text=(
            "Foreign key as a relation to the corresponding Docket "
            "object. Specifies which docket the docket entry "
            "belongs to."
        ),
        related_name="docket_entries",
        on_delete=models.CASCADE,
    )
    tags = models.ManyToManyField(
        "search.Tag",
        help_text="The tags associated with the docket entry.",
        related_name="docket_entries",
        blank=True,
    )
    html_documents = GenericRelation(
        "recap.PacerHtmlFiles",
        help_text="HTML attachment files collected from PACER.",
        related_query_name="docket_entries",
        null=True,
        blank=True,
    )
    date_filed = models.DateField(
        help_text=(
            "The created date of the Docket Entry according to the "
            "court timezone."
        ),
        null=True,
        blank=True,
    )
    time_filed = models.TimeField(
        help_text=(
            "The created time of the Docket Entry according to the court "
            "timezone, null if no time data is available."
        ),
        null=True,
        blank=True,
    )
    entry_number = models.BigIntegerField(
        help_text=(
            "# on the PACER docket page. For appellate cases, this may "
            "be the internal PACER ID for the document, when an entry "
            "ID is otherwise unavailable."
        ),
        null=True,
        blank=True,
    )
    recap_sequence_number = models.CharField(
        help_text=(
            "A field used for ordering the docket entries on a docket. "
            'You might wonder, "Why not use the docket entry '
            "numbers?\" That's a reasonable question, and prior to late "
            "2018, this was the method we used. However, dockets often "
            'have "unnumbered" docket entries, and so knowing where '
            "to put those was only possible if you had another "
            "sequencing field, since they lacked an entry number. This "
            "field is populated by a combination of the date for the "
            "entry and a sequence number indicating the order that the "
            "unnumbered entries occur."
        ),
        max_length=50,
        blank=True,
    )
    pacer_sequence_number = models.IntegerField(
        help_text=(
            "The de_seqno value pulled out of dockets, RSS feeds, and "
            "sundry other pages in PACER. The place to find this is "
            "currently in the onclick attribute of the links in PACER. "
            "Because we do not have this value for all items in the DB, "
            "we do not use this value for anything. Still, we collect "
            "it for good measure."
        ),
        null=True,
        blank=True,
    )
    description = models.TextField(
        help_text=(
            "The text content of the docket entry that appears in the "
            "PACER docket page."
        ),
        blank=True,
    )
    es_rd_field_tracker = FieldTracker(
        fields=[
            "description",
            "entry_number",
            "date_filed",
        ]
    )

    class Meta:
        verbose_name_plural = "Docket Entries"
        indexes = [
            models.Index(
                fields=["docket_id", "entry_number"],
                name="entry_number_idx",
                condition=Q(entry_number=1),
            ),
            models.Index(
                fields=["recap_sequence_number", "entry_number"],
                name="search_docketentry_recap_sequence_number_1c82e51988e2d89f_idx",
            ),
        ]
        ordering = ("recap_sequence_number", "entry_number")
        permissions = (("has_recap_api_access", "Can work with RECAP API"),)

    def __str__(self) -> str:
        return f"{self.pk} ---> {trunc(self.description, 50, ellipsis='...')}"

    @property
    def datetime_filed(self) -> datetime | None:
        if self.time_filed:
            from cl.recap.constants import COURT_TIMEZONES

            local_timezone = pytz.timezone(
                COURT_TIMEZONES.get(self.docket.court.id, "US/Eastern")
            )
            return local_timezone.localize(
                datetime.combine(self.date_filed, self.time_filed)
            )
        return None

    def get_csv_columns(self, get_column_name=False):
        columns = [
            "id",
            "entry_number",
            "date_filed",
            "time_filed",
            "pacer_sequence_number",
            "recap_sequence_number",
            "description",
        ]
        if get_column_name:
            columns = [self.add_class_name(col) for col in columns]
        return columns

    def get_column_function(self):
        """Get dict of attrs: fucntion to apply on field value if it needs
        to be pre-processed before being add to csv

        returns: dict -- > {attr1: function}"""
        return {}


@pghistory.track(
    pghistory.InsertEvent(), pghistory.DeleteEvent(), obj_field=None
)
class DocketEntryTags(DocketEntry.tags.through):
    """A model class to track docket entry tags m2m relation"""

    class Meta:
        proxy = True


class AbstractPacerDocument(models.Model):
    date_upload = models.DateTimeField(
        help_text=(
            "upload_date in RECAP. The date the file was uploaded to "
            "RECAP. This information is provided by RECAP."
        ),
        blank=True,
        null=True,
    )
    document_number = models.CharField(
        help_text=(
            "If the file is a document, the number is the "
            "document_number in RECAP docket."
        ),
        max_length=32,
        db_index=True,
        blank=True,  # To support unnumbered minute entries
    )
    attachment_number = models.SmallIntegerField(
        help_text=(
            "If the file is an attachment, the number is the attachment "
            "number in RECAP docket."
        ),
        blank=True,
        null=True,
    )
    pacer_doc_id = models.CharField(
        help_text="The ID of the document in PACER.",
        max_length=64,  # Increased to support storing docketEntryId from ACMS.
        blank=True,
    )
    is_available = models.BooleanField(
        help_text="True if the item is available in RECAP",
        blank=True,
        null=True,
        default=False,
    )
    is_free_on_pacer = models.BooleanField(
        help_text="Is this item freely available as an opinion on PACER?",
        db_index=True,
        null=True,
    )
    is_sealed = models.BooleanField(
        help_text="Is this item sealed or otherwise unavailable on PACER?",
        null=True,
    )

    class Meta:
        abstract = True


@pghistory.track()
class RECAPDocument(
    AbstractPacerDocument, AbstractPDF, AbstractDateTimeModel, CSVExportMixin
):
    """The model for Docket Documents and Attachments."""

    PACER_DOCUMENT = 1
    ATTACHMENT = 2
    DOCUMENT_TYPES = (
        (PACER_DOCUMENT, "PACER Document"),
        (ATTACHMENT, "Attachment"),
    )
    docket_entry = models.ForeignKey(
        DocketEntry,
        help_text=(
            "Foreign Key to the DocketEntry object to which it belongs. "
            "Multiple documents can belong to a DocketEntry. "
            "(Attachments and Documents together)"
        ),
        related_name="recap_documents",
        on_delete=models.CASCADE,
    )
    tags = models.ManyToManyField(
        "search.Tag",
        help_text="The tags associated with the document.",
        related_name="recap_documents",
        blank=True,
    )
    document_type = models.IntegerField(
        help_text="Whether this is a regular document or an attachment.",
        choices=DOCUMENT_TYPES,
    )
    description = models.TextField(
        help_text=(
            "The short description of the docket entry that appears on "
            "the attachments page."
        ),
        blank=True,
    )
    acms_document_guid = models.CharField(
        help_text="The GUID of the document in ACMS.",
        max_length=64,
        blank=True,
    )

    es_rd_field_tracker = FieldTracker(
        fields=[
            "docket_entry_id",
            "document_type",
            "document_number",
            "description",
            "pacer_doc_id",
            "plain_text",
            "attachment_number",
            "is_available",
            "page_count",
            "filepath_local",
        ]
    )

    class Meta:
        unique_together = (
            "docket_entry",
            "document_number",
            "attachment_number",
        )
        ordering = ("document_type", "document_number", "attachment_number")
        indexes = [
            models.Index(
                fields=[
                    "document_type",
                    "document_number",
                    "attachment_number",
                ],
                name="search_recapdocument_document_type_303cccac79571217_idx",
            ),
            models.Index(
                fields=["filepath_local"],
                name="search_recapdocument_filepath_local_7dc6b0e53ccf753_uniq",
            ),
            models.Index(
                fields=["pacer_doc_id"],
                name="pacer_doc_id_idx",
                condition=~Q(pacer_doc_id=""),
            ),
        ]
        permissions = (("has_recap_api_access", "Can work with RECAP API"),)

    def __str__(self) -> str:
        return "%s: Docket_%s , document_number_%s , attachment_number_%s" % (
            self.pk,
            self.docket_entry.docket.docket_number,
            self.document_number,
            self.attachment_number,
        )

    def get_absolute_url(self) -> str:
        if not self.document_number:
            # Numberless entries don't get URLs
            return ""
        if self.document_type == self.PACER_DOCUMENT:
            return reverse(
                "view_recap_document",
                kwargs={
                    "docket_id": self.docket_entry.docket.pk,
                    "doc_num": self.document_number,
                    "slug": self.docket_entry.docket.slug,
                },
            )
        elif self.document_type == self.ATTACHMENT:
            return reverse(
                "view_recap_attachment",
                kwargs={
                    "docket_id": self.docket_entry.docket.pk,
                    "doc_num": self.document_number,
                    "att_num": self.attachment_number,
                    "slug": self.docket_entry.docket.slug,
                },
            )

    def get_authorities_url(self) -> str:
        if self.document_type == self.ATTACHMENT:
            return reverse(
                "view_attachment_authorities",
                kwargs={
                    "docket_id": self.docket_entry.docket.pk,
                    "doc_num": self.document_number,
                    "att_num": self.attachment_number,
                    "slug": self.docket_entry.docket.slug,
                },
            )
        else:
            return reverse(
                "view_document_authorities",
                kwargs={
                    "docket_id": self.docket_entry.docket.pk,
                    "doc_num": self.document_number,
                    "slug": self.docket_entry.docket.slug,
                },
            )

    @property
    def pacer_url(self) -> str | None:
        """Construct a doc1 URL for any item, if we can. Else, return None."""
        from cl.lib.pacer import map_cl_to_pacer_id

        court = self.docket_entry.docket.court
        court_id = map_cl_to_pacer_id(court.pk)
        if self.pacer_doc_id:
            if self.pacer_doc_id.count("-") > 1:
                return (
                    f"https://{court_id}-showdoc.azurewebsites.us/docs/"
                    f"{self.docket_entry.docket.pacer_case_id}/"
                    f"{self.pacer_doc_id}"
                )
            elif court.jurisdiction == Court.FEDERAL_APPELLATE:
                template = "https://ecf.%s.uscourts.gov/docs1/%s?caseId=%s"
            else:
                template = "https://ecf.%s.uscourts.gov/doc1/%s?caseid=%s"
            return template % (
                court_id,
                self.pacer_doc_id,
                self.docket_entry.docket.pacer_case_id,
            )
        else:
            if court.jurisdiction == Court.FEDERAL_APPELLATE:
                return ""
            else:
                attachment_number = self.attachment_number or ""
                return (
                    "https://ecf.{court_id}.uscourts.gov/cgi-bin/"
                    "show_case_doc?"
                    "{document_number},"
                    "{pacer_case_id},"
                    "{attachment_number},"
                    "{magic_number},".format(
                        court_id=court_id,
                        document_number=self.document_number,
                        pacer_case_id=self.docket_entry.docket.pacer_case_id,
                        attachment_number=attachment_number,
                        magic_number="",  # For future use.
                    )
                )

    @property
    def has_valid_pdf(self) -> bool:
        return self.is_available and self.filepath_local

    @property
    def needs_extraction(self):
        """Does the item need extraction and does it have all the right
        fields? Items needing OCR still need extraction.
        """
        return all(
            [
                self.ocr_status is None or self.ocr_status == self.OCR_NEEDED,
                self.has_valid_pdf,
            ]
        )

    @property
    def authority_count(self):
        return self.cited_opinions.count()

    @property
    def authorities_with_data(self):
        """Returns a queryset of this document's authorities for
        eventual injection into a view template.

        The returned queryset is sorted by the depth field.
        """
        return build_authorities_query(self.cited_opinions)

    def save(
        self,
        update_fields=None,
        do_extraction=False,
        index=False,
        *args,
        **kwargs,
    ):
        self.clean()

        if self.pacer_doc_id is None:
            # Juriscraper returns these as null values. Instead we want blanks.
            self.pacer_doc_id = ""

        if self.attachment_number is None:
            # Validate that we don't already have such an entry. This is needed
            # because None values in SQL are all considered different.
            others = RECAPDocument.objects.exclude(pk=self.pk).filter(
                document_number=self.document_number,
                attachment_number=self.attachment_number,
                docket_entry=self.docket_entry,
            )
            if others.exists():
                # Keep only the better item. This situation occurs during race
                # conditions since the check we do here doesn't have the kinds
                # of database guarantees we would like. Items are duplicates if
                # they have the same pacer_doc_id. The worse one is the one
                # that is *not* being updated here.
                if others.count() > 1:
                    raise ValidationError(
                        "Multiple duplicate values violate save constraint "
                        "and we are unable to fix it automatically for "
                        "rd: %s" % self.pk
                    )
                else:
                    # Only one duplicate. Attempt auto-resolution.
                    other = others[0]
                if other.pacer_doc_id == self.pacer_doc_id:
                    # Delete "other"; the new one probably has better data.
                    # Lots of code could be written here to merge "other" into
                    # self, but it's nasty stuff because it happens when saving
                    # new data and requires merging a lot of fields. This
                    # situation only occurs rarely, so just delete "other" and
                    # hope that "self" has the best, latest data.
                    other.delete()
                else:
                    raise ValidationError(
                        "Duplicate values violate save constraint and we are "
                        "unable to fix it because the items have different "
                        "pacer_doc_id values. The rds are %s and %s "
                        % (self.pk, other.pk)
                    )

        if update_fields is not None:
            update_fields = {"pacer_doc_id"}.union(update_fields)

        super().save(update_fields=update_fields, *args, **kwargs)
        tasks = []
        if do_extraction and self.needs_extraction:
            # Context extraction not done and is requested.
            from cl.scrapers.tasks import extract_recap_pdf

            tasks.append(extract_recap_pdf.si(self.pk))

        if len(tasks) > 0:
            chain(*tasks)()

    async def asave(
        self,
        update_fields=None,
        do_extraction=False,
        index=False,
        *args,
        **kwargs,
    ):
        return await sync_to_async(self.save)(
            update_fields=update_fields,
            do_extraction=do_extraction,
            index=index,
            *args,
            **kwargs,
        )

    def clean(self):
        """
        Validate that:
        - Attachments must have an attachment_number.
        - Main PACER documents must not have an attachment_number.
        """
        super().clean()
        is_attachment = self.document_type == self.ATTACHMENT
        has_attachment_number = self.attachment_number is not None
        missing_attachment_number = is_attachment and not has_attachment_number
        wrongly_added_att_num = not is_attachment and has_attachment_number
        if missing_attachment_number or wrongly_added_att_num:
            msg = (
                "attachment_number cannot be null for an attachment."
                if missing_attachment_number
                else "attachment_number must be null for a main PACER document."
            )
            logger.error(msg)
            raise ValidationError({"attachment_number": msg})

    def get_csv_columns(self, get_column_name=False):
        columns = [
            "id",
            "document_type",
            "description",
            "acms_document_guid",
            "date_upload",
            "document_number",
            "attachment_number",
            "pacer_doc_id",
            "is_free_on_pacer",
            "is_available",
            "is_sealed",
            "sha1",
            "page_count",
            "file_size",
            "filepath_local",
            "filepath_ia",
            "ocr_status",
        ]
        if get_column_name:
            columns = [self.add_class_name(col) for col in columns]
        return columns

    def _get_readable_document_type(self, *args, **kwargs):
        return self.get_document_type_display()

    def _get_readable_ocr_status(self, *args, **kwargs):
        return self.get_ocr_status_display()

    def _get_full_filepath_local(self, *args, **kwargs):
        if self.filepath_local:
            return f"https://storage.courtlistener.com/{self.filepath_local}"
        return ""

    def get_column_function(self):
        """Get dict of attrs: function to apply on field value if it needs
        to be pre-processed before being add to csv
        If not functions returns empty dict

        returns: dict -- > {attr1: function}"""
        return {
            "document_type": self._get_readable_document_type,
            "ocr_status": self._get_readable_ocr_status,
            "filepath_local": self._get_full_filepath_local,
        }


@pghistory.track(
    pghistory.InsertEvent(), pghistory.DeleteEvent(), obj_field=None
)
class RECAPDocumentTags(RECAPDocument.tags.through):
    """A model class to track recap document tags m2m relation"""

    class Meta:
        proxy = True


@pghistory.track()
class BankruptcyInformation(AbstractDateTimeModel):
    docket = models.OneToOneField(
        Docket,
        help_text="The docket that the bankruptcy info is associated with.",
        on_delete=models.CASCADE,
        related_name="bankruptcy_information",
    )
    date_converted = models.DateTimeField(
        help_text=(
            "The date when the bankruptcy was converted from one "
            "chapter to another."
        ),
        blank=True,
        null=True,
    )
    date_last_to_file_claims = models.DateTimeField(
        help_text="The last date for filing claims.", blank=True, null=True
    )
    date_last_to_file_govt = models.DateTimeField(
        help_text="The last date for the government to file claims.",
        blank=True,
        null=True,
    )
    date_debtor_dismissed = models.DateTimeField(
        help_text="The date the debtor was dismissed.", blank=True, null=True
    )
    chapter = models.CharField(
        help_text="The chapter the bankruptcy is currently filed under.",
        max_length=10,
        blank=True,
    )
    trustee_str = models.TextField(
        help_text="The name of the trustee handling the case.", blank=True
    )
    es_rd_field_tracker = FieldTracker(
        fields=[
            "chapter",
            "trustee_str",
        ]
    )

    class Meta:
        verbose_name_plural = "Bankruptcy Information"

    def __str__(self) -> str:
        return f"Bankruptcy Info for docket {self.docket_id}"


@pghistory.track()
class Claim(AbstractDateTimeModel):
    docket = models.ForeignKey(
        Docket,
        help_text="The docket that the claim is associated with.",
        related_name="claims",
        on_delete=models.CASCADE,
    )
    tags = models.ManyToManyField(
        "search.Tag",
        help_text="The tags associated with the document.",
        related_name="claims",
        blank=True,
    )
    date_claim_modified = models.DateTimeField(
        help_text="Date the claim was last modified to our knowledge.",
        blank=True,
        null=True,
    )
    date_original_entered = models.DateTimeField(
        help_text="Date the claim was originally entered.",
        blank=True,
        null=True,
    )
    date_original_filed = models.DateTimeField(
        help_text="Date the claim was originally filed.",
        blank=True,
        null=True,
    )
    date_last_amendment_entered = models.DateTimeField(
        help_text="Date the last amendment was entered.",
        blank=True,
        null=True,
    )
    date_last_amendment_filed = models.DateTimeField(
        help_text="Date the last amendment was filed.", blank=True, null=True
    )
    claim_number = models.CharField(
        help_text="The number of the claim.",
        max_length=10,
        blank=True,
        db_index=True,
    )
    creditor_details = models.TextField(
        help_text=(
            "The details of the creditor from the claims register; "
            "typically their address."
        ),
        blank=True,
    )
    creditor_id = models.CharField(
        help_text=(
            "The ID of the creditor from the claims register; "
            "typically a seven digit number"
        ),
        max_length=50,
        blank=True,
    )
    status = models.CharField(
        help_text="The status of the claim.", max_length=1000, blank=True
    )
    entered_by = models.CharField(
        help_text="The person that entered the claim.",
        max_length=1000,
        blank=True,
    )
    filed_by = models.CharField(
        help_text="The person that filed the claim.",
        max_length=1000,
        blank=True,
    )
    # An additional field, admin_claimed, should be added here eventually too.
    # It's ready in Juriscraper, but rarely used and skipped for the moment.
    amount_claimed = models.CharField(
        help_text="The amount claimed, usually in dollars.",
        max_length=100,
        blank=True,
    )
    unsecured_claimed = models.CharField(
        help_text="The unsecured claimed, usually in dollars.",
        max_length=100,
        blank=True,
    )
    secured_claimed = models.CharField(
        help_text="The secured claimed, usually in dollars.",
        max_length=100,
        blank=True,
    )
    priority_claimed = models.CharField(
        help_text="The priority claimed, usually in dollars.",
        max_length=100,
        blank=True,
    )
    description = models.TextField(
        help_text=(
            "The description of the claim that appears on the claim "
            "register."
        ),
        blank=True,
    )
    remarks = models.TextField(
        help_text=(
            "The remarks of the claim that appear on the claim " "register."
        ),
        blank=True,
    )

    def __str__(self) -> str:
        return "Claim #%s on docket %s with pk %s" % (
            self.claim_number,
            self.docket_id,
            self.pk,
        )


@pghistory.track(
    pghistory.InsertEvent(), pghistory.DeleteEvent(), obj_field=None
)
class ClaimTags(Claim.tags.through):
    """A model class to track claim tags m2m relation"""

    class Meta:
        proxy = True


@pghistory.track()
class ClaimHistory(AbstractPacerDocument, AbstractPDF, AbstractDateTimeModel):
    DOCKET_ENTRY = 1
    CLAIM_ENTRY = 2
    CLAIM_TYPES = (
        (DOCKET_ENTRY, "A docket entry referenced from the claim register."),
        (CLAIM_ENTRY, "A document only referenced from the claim register"),
    )
    claim = models.ForeignKey(
        Claim,
        help_text="The claim that the history row is associated with.",
        related_name="claim_history_entries",
        on_delete=models.CASCADE,
    )
    date_filed = models.DateField(
        help_text="The created date of the claim.", null=True, blank=True
    )
    claim_document_type = models.IntegerField(
        help_text=(
            "The type of document that is used in the history row for "
            "the claim. One of: %s"
        )
        % ", ".join([f"{t[0]} ({t[1]})" for t in CLAIM_TYPES]),
        choices=CLAIM_TYPES,
    )
    description = models.TextField(
        help_text=(
            "The text content of the docket entry that appears in the "
            "docket or claims registry page."
        ),
        blank=True,
    )
    # Items should either have a claim_doc_id or a pacer_doc_id, depending on
    # their claim_document_type value.
    claim_doc_id = models.CharField(
        help_text="The ID of a claims registry document.",
        max_length=32,  # Same as in RECAP
        blank=True,
    )
    pacer_dm_id = models.IntegerField(
        help_text=(
            "The dm_id value pulled out of links and possibly other "
            "pages in PACER. Collected but not currently used."
        ),
        null=True,
        blank=True,
    )
    pacer_case_id = models.CharField(
        help_text=(
            "The case ID provided by PACER. Noted in this case on a "
            "per-document-level, since we've learned that some "
            "documents from other cases can appear in curious places."
        ),
        max_length=100,
        blank=True,
    )

    class Meta:
        verbose_name_plural = "Claim History Entries"


class FederalCourtsQuerySet(models.QuerySet):
    def all(self) -> models.QuerySet:
        return self.filter(jurisdiction__in=Court.FEDERAL_JURISDICTIONS)

    def all_pacer_courts(self) -> models.QuerySet:
        return self.filter(
            Q(
                jurisdiction__in=[
                    Court.FEDERAL_DISTRICT,
                    Court.FEDERAL_BANKRUPTCY,
                    Court.FEDERAL_APPELLATE,
                ]
            )
            | Q(pk__in=["cit", "jpml", "uscfc", "cavc"]),
            end_date__isnull=True,
        ).exclude(pk="scotus")

    def district_or_bankruptcy_pacer_courts(self) -> models.QuerySet:
        return self.filter(
            Q(
                jurisdiction__in=[
                    Court.FEDERAL_DISTRICT,
                    Court.FEDERAL_BANKRUPTCY,
                ]
            )
            | Q(pk__in=["cit", "jpml", "uscfc"]),
            end_date__isnull=True,
        )

    def appellate_pacer_courts(self) -> models.QuerySet:
        return self.filter(
            Q(jurisdiction=Court.FEDERAL_APPELLATE) |
            # Court of Appeals for Veterans Claims uses appellate PACER
            Q(pk__in=["cavc"]),
            end_date__isnull=True,
        ).exclude(pk="scotus")

    def bankruptcy_pacer_courts(self) -> models.QuerySet:
        return self.filter(
            jurisdiction=Court.FEDERAL_BANKRUPTCY, end_date__isnull=True
        )

    def district_courts(self) -> models.QuerySet:
        return self.filter(jurisdiction=Court.FEDERAL_DISTRICT)

    def bankruptcy_courts(self) -> models.QuerySet:
        return self.filter(jurisdictions__in=Court.BANKRUPTCY_JURISDICTIONS)

    def appellate_courts(self) -> models.QuerySet:
        return self.filter(jurisdiction=Court.FEDERAL_APPELLATE)

    def tribal_courts(self) -> models.QuerySet:
        return self.filter(jurisdictions__in=Court.TRIBAL_JURISDICTIONS)

    def territorial_courts(self) -> models.QuerySet:
        return self.filter(jurisdictions__in=Court.TERRITORY_JURISDICTIONS)

    def military_courts(self) -> models.QuerySet:
        return self.filter(jurisdictions__in=Court.MILITARY_JURISDICTIONS)


@pghistory.track()
class Court(models.Model):
    """A class to represent some information about each court, can be extended
    as needed."""

    # Note that spaces cannot be used in the keys, or else the SearchForm won't
    # work
    FEDERAL_APPELLATE = "F"
    FEDERAL_DISTRICT = "FD"
    FEDERAL_BANKRUPTCY = "FB"
    FEDERAL_BANKRUPTCY_PANEL = "FBP"
    FEDERAL_SPECIAL = "FS"
    STATE_SUPREME = "S"
    STATE_APPELLATE = "SA"
    STATE_TRIAL = "ST"
    STATE_SPECIAL = "SS"
    STATE_ATTORNEY_GENERAL = "SAG"
    TRIBAL_SUPREME = "TRS"
    TRIBAL_APPELLATE = "TRA"
    TRIBAL_TRIAL = "TRT"
    TRIBAL_SPECIAL = "TRX"
    TERRITORY_SUPREME = "TS"
    TERRITORY_APPELLATE = "TA"
    TERRITORY_TRIAL = "TT"
    TERRITORY_SPECIAL = "TSP"
    MILITARY_APPELLATE = "MA"
    MILITARY_TRIAL = "MT"
    COMMITTEE = "C"
    INTERNATIONAL = "I"
    TESTING_COURT = "T"
    JURISDICTIONS = (
        (FEDERAL_APPELLATE, "Federal Appellate"),
        (FEDERAL_DISTRICT, "Federal District"),
        (FEDERAL_BANKRUPTCY, "Federal Bankruptcy"),
        (FEDERAL_BANKRUPTCY_PANEL, "Federal Bankruptcy Panel"),
        (FEDERAL_SPECIAL, "Federal Special"),
        (STATE_SUPREME, "State Supreme"),
        (STATE_APPELLATE, "State Appellate"),
        (STATE_TRIAL, "State Trial"),
        (STATE_SPECIAL, "State Special"),
        (TRIBAL_SUPREME, "Tribal Supreme"),
        (TRIBAL_APPELLATE, "Tribal Appellate"),
        (TRIBAL_TRIAL, "Tribal Trial"),
        (TRIBAL_SPECIAL, "Tribal Special"),
        (TERRITORY_SUPREME, "Territory Supreme"),
        (TERRITORY_APPELLATE, "Territory Appellate"),
        (TERRITORY_TRIAL, "Territory Trial"),
        (TERRITORY_SPECIAL, "Territory Special"),
        (STATE_ATTORNEY_GENERAL, "State Attorney General"),
        (MILITARY_APPELLATE, "Military Appellate"),
        (MILITARY_TRIAL, "Military Trial"),
        (COMMITTEE, "Committee"),
        (INTERNATIONAL, "International"),
        (TESTING_COURT, "Testing"),
    )
    FEDERAL_JURISDICTIONS = [
        FEDERAL_APPELLATE,
        FEDERAL_DISTRICT,
        FEDERAL_SPECIAL,
        FEDERAL_BANKRUPTCY,
        FEDERAL_BANKRUPTCY_PANEL,
    ]
    STATE_JURISDICTIONS = [
        STATE_SUPREME,
        STATE_APPELLATE,
        STATE_TRIAL,
        STATE_SPECIAL,
        STATE_ATTORNEY_GENERAL,
    ]
    BANKRUPTCY_JURISDICTIONS = [
        FEDERAL_BANKRUPTCY,
        FEDERAL_BANKRUPTCY_PANEL,
    ]
    TRIBAL_JURISDICTIONS = [
        TRIBAL_SUPREME,
        TRIBAL_APPELLATE,
        TRIBAL_TRIAL,
        TRIBAL_SPECIAL,
    ]
    TERRITORY_JURISDICTIONS = [
        TERRITORY_SUPREME,
        TERRITORY_APPELLATE,
        TERRITORY_TRIAL,
        TERRITORY_SPECIAL,
    ]
    MILITARY_JURISDICTIONS = [
        MILITARY_APPELLATE,
        MILITARY_TRIAL,
    ]

    id = models.CharField(
        help_text="a unique ID for each court as used in URLs",
        max_length=15,  # Changes here will require updates in urls.py
        primary_key=True,
    )
    parent_court = models.ForeignKey(
        "self",
        help_text="Parent court for subdivisions",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="child_courts",
    )
    appeals_to = models.ManyToManyField(
        "self",
        help_text="Appellate courts for this court",
        blank=True,
        symmetrical=False,
        related_name="appeals_from",
    )
    # Pacer fields
    pacer_court_id = models.PositiveSmallIntegerField(
        help_text=(
            "The numeric ID for the court in PACER. "
            "This can be found by looking at the first three "
            "digits of any doc1 URL in PACER."
        ),
        null=True,
        blank=True,
    )
    pacer_has_rss_feed = models.BooleanField(
        help_text=(
            "Whether the court has a PACER RSS feed. If null, this "
            "doesn't apply to the given court."
        ),
        blank=True,
        null=True,
    )
    pacer_rss_entry_types = models.TextField(
        help_text="The types of entries provided by the court's RSS feed.",
        blank=True,
    )
    date_last_pacer_contact = models.DateTimeField(
        help_text="The last time the PACER website for the court was "
        "successfully contacted",
        blank=True,
        null=True,
    )

    # Other stuff
    fjc_court_id = models.CharField(
        help_text="The ID used by FJC in the Integrated Database",
        max_length=3,
        blank=True,
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified",
        auto_now=True,
        db_index=True,
    )
    in_use = models.BooleanField(
        help_text=(
            "Whether this jurisdiction is in use in CourtListener -- "
            "increasingly True"
        ),
        default=False,
    )
    has_opinion_scraper = models.BooleanField(
        help_text=(
            "Whether the jurisdiction has a scraper that obtains "
            "opinions automatically."
        ),
        default=False,
    )
    has_oral_argument_scraper = models.BooleanField(
        help_text=(
            "Whether the jurisdiction has a scraper that obtains oral "
            "arguments automatically."
        ),
        default=False,
    )
    position = models.FloatField(
        help_text=(
            "A dewey-decimal-style numeral indicating a hierarchical "
            "ordering of jurisdictions"
        ),
        db_index=True,
        unique=True,
    )
    citation_string = models.CharField(
        help_text="the citation abbreviation for the court "
        "as dictated by Blue Book",
        max_length=100,
        blank=True,
    )
    short_name = models.CharField(
        help_text="a short name of the court", max_length=100, blank=False
    )
    full_name = models.CharField(
        help_text="the full name of the court", max_length=200, blank=False
    )
    url = models.URLField(
        help_text="the homepage for each court or the closest thing thereto",
        max_length=500,
        blank=True,
    )
    start_date = models.DateField(
        help_text="the date the court was established, if known",
        blank=True,
        null=True,
    )
    end_date = models.DateField(
        help_text="the date the court was abolished, if known",
        blank=True,
        null=True,
    )
    jurisdiction = models.CharField(
        help_text="the jurisdiction of the court, one of: %s"
        % ", ".join(f"{t[0]} ({t[1]})" for t in JURISDICTIONS),
        max_length=3,
        choices=JURISDICTIONS,
    )
    notes = models.TextField(
        help_text="any notes about coverage or anything else (currently very "
        "raw)",
        blank=True,
    )

    objects = models.Manager()
    federal_courts = FederalCourtsQuerySet.as_manager()

    def __str__(self) -> str:
        return f"{self.full_name}"

    @property
    def is_terminated(self):
        if self.end_date:
            return True
        return False

    class Meta:
        ordering = ["position"]


@pghistory.track(
    pghistory.InsertEvent(), pghistory.DeleteEvent(), obj_field=None
)
class CourtAppealsTo(Court.appeals_to.through):
    """A model class to track court appeals_to m2m relation"""

    class Meta:
        proxy = True


@pghistory.track()
class Courthouse(models.Model):
    """A class to represent the physical location of a court."""

    COUNTRY_CHOICES = (("GB", "United Kingdom"), ("US", "United States"))

    court = models.ForeignKey(
        Court,
        help_text="The court object associated with this courthouse.",
        related_name="courthouses",
        on_delete=models.CASCADE,
    )
    court_seat = models.BooleanField(
        help_text="Is this the seat of the Court?",
        default=False,
        null=True,
    )
    building_name = models.TextField(
        help_text="Ex. John Adams Courthouse.",
        blank=True,
    )
    address1 = models.TextField(
        help_text="The normalized address1 of the courthouse.",
        blank=True,
    )
    address2 = models.TextField(
        help_text="The normalized address2 of the courthouse.",
        blank=True,
    )
    city = models.TextField(
        help_text="The normalized city of the courthouse.",
        blank=True,
    )
    county = models.TextField(
        help_text="The county, if any, where the courthouse resides.",
        blank=True,
    )
    state = USPostalCodeField(
        help_text="The two-letter USPS postal abbreviation for the "
        "organization w/ obsolete state options.",
        choices=USPS_CHOICES + OBSOLETE_STATES,
        blank=True,
    )
    zip_code = USZipCodeField(
        help_text="The zip code for the organization, XXXXX or XXXXX-XXXX "
        "work.",
        blank=True,
    )
    country_code = models.TextField(
        help_text="The two letter country code.",
        choices=COUNTRY_CHOICES,
        default="US",
    )

    def __str__(self):
        return f"{self.court.short_name} Courthouse"

    class Meta:
        verbose_name_plural = "Courthouses"


class ClusterCitationQuerySet(models.query.QuerySet):
    """Add filtering on citation strings.

    Historically we had citations in the db as strings like, "22 U.S. 44". The
    nice thing about that was that it was fairly easy to look them up. The new
    way breaks citations into volume-reporter-page tuples. That's great for
    granularity, but it makes it harder to look things up.

    This class attempts to fix that by overriding the usual filter, adding an
    additional kwarg that can be provided:

        Citation.object.filter(citation='22 U.S. 44')

    That makes it a lot easier to do the kinds of filtering we're used to.
    """

    def filter(self, *args, **kwargs):
        clone = self._clone()
        citation_str = kwargs.pop("citation", None)
        if citation_str:
            try:
                c = get_citations(
                    citation_str,
                    remove_ambiguous=False,
                    tokenizer=HYPERSCAN_TOKENIZER,
                )[0]
            except IndexError:
                raise ValueError(f"Unable to parse citation '{citation_str}'")
            else:
                clone.query.add_q(
                    Q(
                        citations__volume=c.groups["volume"],
                        citations__reporter=c.corrected_reporter(),
                        citations__page=c.groups["page"],
                    )
                )

        # Add the rest of the args & kwargs
        clone.query.add_q(Q(*args, **kwargs))
        return clone


@pghistory.track()
class OpinionCluster(AbstractDateTimeModel):
    """A class representing a cluster of court opinions."""

    SCDB_DECISION_DIRECTIONS = (
        (1, "Conservative"),
        (2, "Liberal"),
        (3, "Unspecifiable"),
    )
    docket = models.ForeignKey(
        Docket,
        help_text="The docket that the opinion cluster is a part of",
        related_name="clusters",
        on_delete=models.CASCADE,
    )
    panel = models.ManyToManyField(
        "people_db.Person",
        help_text="The judges that participated in the opinion",
        related_name="opinion_clusters_participating_judges",
        blank=True,
    )
    non_participating_judges = models.ManyToManyField(
        "people_db.Person",
        help_text="The judges that heard the case, but did not participate in "
        "the opinion",
        related_name="opinion_clusters_non_participating_judges",
        blank=True,
    )
    judges = models.TextField(
        help_text=(
            "The judges that participated in the opinion as a simple "
            "text string. This field is used when normalized judges "
            "cannot be placed into the panel field."
        ),
        blank=True,
    )
    date_filed = models.DateField(
        help_text="The date the cluster of opinions was filed by the court",
        db_index=True,
    )
    date_filed_is_approximate = models.BooleanField(
        help_text=(
            "For a variety of opinions getting the correct date filed is"
            "very difficult. For these, we have used heuristics to "
            "approximate the date."
        ),
        default=False,
    )
    slug = models.SlugField(
        help_text="URL that the document should map to (the slug)",
        max_length=75,
        db_index=False,
        null=True,
    )
    case_name_short = models.TextField(
        help_text="The abridged name of the case, often a single word, e.g. "
        "'Marsh'",
        blank=True,
    )
    case_name = models.TextField(
        help_text="The shortened name of the case", blank=True
    )
    case_name_full = models.TextField(
        help_text="The full name of the case", blank=True
    )
    scdb_id = models.CharField(
        help_text="The ID of the item in the Supreme Court Database",
        max_length=10,
        db_index=True,
        blank=True,
    )
    scdb_decision_direction = models.IntegerField(
        help_text=(
            'the ideological "direction" of a decision in the Supreme '
            "Court database. More details at: http://scdb.wustl.edu/"
            "documentation.php?var=decisionDirection"
        ),
        choices=SCDB_DECISION_DIRECTIONS,
        blank=True,
        null=True,
    )
    scdb_votes_majority = models.IntegerField(
        help_text=(
            "the number of justices voting in the majority in a Supreme "
            "Court decision. More details at: http://scdb.wustl.edu/"
            "documentation.php?var=majVotes"
        ),
        blank=True,
        null=True,
    )
    scdb_votes_minority = models.IntegerField(
        help_text=(
            "the number of justices voting in the minority in a Supreme "
            "Court decision. More details at: http://scdb.wustl.edu/"
            "documentation.php?var=minVotes"
        ),
        blank=True,
        null=True,
    )
    source = models.CharField(
        help_text="the source of the cluster, one of: %s"
        % ", ".join(f"{t[0]} ({t[1]})" for t in SOURCES.NAMES),
        max_length=10,
        choices=SOURCES.NAMES,
        blank=True,
    )
    procedural_history = models.TextField(
        help_text="The history of the case as it jumped from court to court",
        blank=True,
    )
    attorneys = models.TextField(
        help_text="The attorneys that argued the case, as free text",
        blank=True,
    )
    nature_of_suit = models.TextField(
        help_text=(
            "The nature of the suit. For the moment can be codes or "
            "laws or whatever"
        ),
        blank=True,
    )
    posture = models.TextField(
        help_text="The procedural posture of the case.", blank=True
    )
    syllabus = models.TextField(
        help_text=(
            "A summary of the issues presented in the case and the " "outcome."
        ),
        blank=True,
    )
    headnotes = models.TextField(
        help_text=(
            "Headnotes are summary descriptions of the legal "
            "issues discussed by the court in the particular case. "
            "They appear at the beginning of each case just after "
            "the summary and disposition. "
            "They are short paragraphs with a heading in bold face type."
            " From Wikipedia - A headnote is a brief summary of a "
            "particular point of law that is added to the text of a court"
            "decision to aid readers in locating discussion of a legal"
            "issue in an opinion. As the term implies, headnotes appear"
            "at the beginning of the published opinion. Frequently, "
            "headnotes are value-added components appended to "
            "decisions by the publisher who compiles the "
            "decisions of a court for resale. As handed down by "
            "the court, a decision or written opinion does not contain "
            "headnotes. These are added later by an editor not "
            "connected to the court, but who instead works for a "
            "legal publishing house."
        ),
        blank=True,
    )
    summary = models.TextField(
        help_text=(
            "A summary of what happened in the case. "
            "Appears at the beginning of the case just "
            "after the title of the case and court "
            "information."
        ),
        blank=True,
    )
    disposition = models.TextField(
        help_text=(
            "Description of the procedural outcome of the case, "
            "e.g. Reversed, dismissed etc. "
            "Generally a short paragraph that appears "
            "just after the summary or synopsis"
        ),
        blank=True,
    )
    history = models.TextField(
        help_text=(
            "History of the case (similar to the summary, "
            "but focused on past events related to this case). "
            "Appears at the beginning of the case just after "
            "the title of the case and court information"
        ),
        blank=True,
    )
    other_dates = models.TextField(
        help_text=(
            "Other date(s) as specified in the text "
            "(case header). This may include follow-up dates."
        ),
        blank=True,
    )
    cross_reference = models.TextField(
        help_text=(
            "Cross-reference citation "
            "(often to a past or future similar case). "
            "It does NOT identify this case."
        ),
        blank=True,
    )
    correction = models.TextField(
        help_text=(
            "Publisher's correction to the case text. "
            "Example: Replace last paragraph on page 476 "
            "with this text: blah blah blah. This is basically an"
            " unstructured text that can be used to manually "
            "correct case content according to publisher's "
            "instructions. No footnotes is expected within it."
        ),
        blank=True,
    )
    citation_count = models.IntegerField(
        help_text=(
            "The number of times this document is cited by other " "opinion"
        ),
        default=0,
        db_index=True,
    )
    precedential_status = models.CharField(
        help_text="The precedential status of document, one of: "
        "%s" % ", ".join([t[0] for t in PRECEDENTIAL_STATUS.NAMES]),
        max_length=50,
        blank=True,
        choices=PRECEDENTIAL_STATUS.NAMES,
        db_index=True,
    )
    date_blocked = models.DateField(
        help_text=(
            "The date that this opinion was blocked from indexing by "
            "search engines"
        ),
        blank=True,
        null=True,
        db_index=True,
    )
    blocked = models.BooleanField(
        help_text=(
            "Whether a document should be blocked from indexing by "
            "search engines"
        ),
        db_index=True,
        default=False,
    )
    filepath_json_harvard = models.FileField(
        help_text=(
            "Path to local storage of JSON collected from Harvard Case "
            "Law project containing available metadata, opinion "
            "and opinion cluster."
        ),
        max_length=1000,
        blank=True,
        db_index=True,
    )
    filepath_pdf_harvard = models.FileField(
        help_text="The case PDF from the Caselaw Access Project for this cluster",
        upload_to=make_upload_path,
        storage=IncrementingAWSMediaStorage(),
        blank=True,
    )
    arguments = models.TextField(
        help_text="The attorney(s) and legal arguments presented as HTML text. "
        "This is primarily seen in older opinions and can contain "
        "case law cited and arguments presented to the judges.",
        blank=True,
    )
    headmatter = models.TextField(
        help_text="Headmatter is the content before an opinion in the Harvard "
        "CaseLaw import. This consists of summaries, headnotes, "
        "attorneys etc for the opinion.",
        blank=True,
    )

    objects = ClusterCitationQuerySet.as_manager()
    es_pa_field_tracker = FieldTracker(
        fields=[
            "case_name",
            "citation_count",
            "date_filed",
            "slug",
            "docket_id",
            "judges",
            "nature_of_suit",
            "precedential_status",
        ]
    )
    es_o_field_tracker = FieldTracker(
        fields=[
            "docket_id",
            "case_name",
            "case_name_short",
            "case_name_full",
            "date_filed",
            "judges",
            "attorneys",
            "nature_of_suit",
            "attorneys",
            "precedential_status",
            "procedural_history",
            "posture",
            "syllabus",
            "scdb_id",
            "citation_count",
            "slug",
            "source",
        ]
    )

    async def acaption(self):
        """Make a proper caption

        This selects the best case name, then combines it with the best one or
        two citations we have in our system. Finally, if it's not a SCOTUS
        opinion, it adds the court abbreviation to the end. The result is
        something like:

            Plessy v. Ferguson, 410 U.S. 113

        or

            Lenore Foman v. Elvira A. Davis (1st Cir. 1961)

        Note that nbsp; are used liberally to prevent the end from getting
        broken up across lines.
        """
        caption = best_case_name(self)
        citation_list = [citation async for citation in self.citations.all()]
        citations = sorted(citation_list, key=sort_cites)
        if not citations:
            docket = await Docket.objects.aget(id=self.docket_id)
            if docket.docket_number:
                caption += f", {docket.docket_number}"
        else:
            if citations[0].type == Citation.NEUTRAL:
                caption += f", {citations[0]}"
                # neutral cites lack the parentheses, so we're done here.
                return caption
            elif (
                len(citations) >= 2
                and citations[0].type == Citation.WEST
                and citations[1].type == Citation.LEXIS
            ):
                caption += f", {citations[0]}, {citations[1]}"
            else:
                caption += f", {citations[0]}"

        docket = await sync_to_async(lambda: self.docket)()
        court = await sync_to_async(lambda: docket.court)()
        if docket.court_id != "scotus":
            court = re.sub(" ", "&nbsp;", court.citation_string)
            # Strftime fails before 1900. Do it this way instead.
            year = self.date_filed.isoformat().split("-")[0]
            caption += f"&nbsp;({court}&nbsp;{year})"
        return caption

    @property
    def caption(self):
        """Make a proper caption

        This selects the best case name, then combines it with the best one or
        two citations we have in our system. Finally, if it's not a SCOTUS
        opinion, it adds the court abbreviation to the end. The result is
        something like:

            Plessy v. Ferguson, 410 U.S. 113

        or

            Lenore Foman v. Elvira A. Davis (1st Cir. 1961)

        Note that nbsp; are used liberally to prevent the end from getting
        broken up across lines.
        """
        caption = best_case_name(self)
        citations = sorted(self.citations.all(), key=sort_cites)
        if not citations:
            if self.docket.docket_number:
                caption += f", {self.docket.docket_number}"
        else:
            if citations[0].type == Citation.NEUTRAL:
                caption += f", {citations[0]}"
                # neutral cites lack the parentheses, so we're done here.
                return caption
            elif (
                len(citations) >= 2
                and citations[0].type == Citation.WEST
                and citations[1].type == Citation.LEXIS
            ):
                caption += f", {citations[0]}, {citations[1]}"
            else:
                caption += f", {citations[0]}"

        if self.docket.court_id != "scotus":
            court = re.sub(" ", "&nbsp;", self.docket.court.citation_string)
            # Strftime fails before 1900. Do it this way instead.
            year = self.date_filed.isoformat().split("-")[0]
            caption += f"&nbsp;({court}&nbsp;{year})"
        return caption

    @property
    def display_citation(self):
        """Find favorite citation to display

        Identify the proper or favorite citation(s) to display on the front end
        but don't wrap it together with a title
        :return: The citation if applicable
        """
        citation_list = [citation for citation in self.citations.all()]
        citations = sorted(citation_list, key=sort_cites)
        if not citations:
            citation = ""
        elif citations[0].type == Citation.NEUTRAL:
            citation = citations[0]
        elif (
            len(citations) >= 2
            and citations[0].type == Citation.WEST
            and citations[1].type == Citation.LEXIS
        ):
            citation = f"{citations[0]}, {citations[1]}"
        else:
            citation = citations[0]
        return citation

    @property
    def citation_string(self):
        """Make a citation string, joined by commas"""
        citations = sorted(self.citations.all(), key=sort_cites)
        return ", ".join(str(c) for c in citations)

    async def acitation_string(self):
        """Make a citation string, joined by commas"""
        result = [citation async for citation in self.citations.all()]
        citations = sorted(result, key=sort_cites)
        return ", ".join(str(c) for c in citations)

    @property
    def authorities(self):
        """Returns a queryset that can be used for querying and caching
        authorities.
        """
        # All clusters that have sub_opinions cited by the sub_opinions of
        # the current cluster, ordered by citation count, descending.
        # Note that:
        #  - sum()'ing an empty list with a nested one, flattens the nested
        #    list.
        #  - QuerySets are lazy by default, so we need to call list() on the
        #    queryset object to evaluate it here and now.
        return OpinionCluster.objects.filter(
            sub_opinions__in=sum(
                [
                    list(sub_opinion.opinions_cited.all().only("pk"))
                    for sub_opinion in self.sub_opinions.all()
                ],
                [],
            )
        ).order_by("-citation_count", "-date_filed")

    async def aauthorities(self):
        """Returns a queryset that can be used for querying and caching
        authorities.
        """
        # All clusters that have sub_opinions cited by the sub_opinions of
        # the current cluster, ordered by citation count, descending.
        # Note that:
        #  - sum()'ing an empty list with a nested one, flattens the nested
        #    list.
        #  - QuerySets are lazy by default, so we need to call list() on the
        #    queryset object to evaluate it here and now.
        return OpinionCluster.objects.filter(
            sub_opinions__in=sum(
                [
                    [
                        i
                        async for i in sub_opinion.opinions_cited.all().only(
                            "pk"
                        )
                    ]
                    async for sub_opinion in self.sub_opinions.all()
                ],
                [],
            )
        ).order_by("-citation_count", "-date_filed")

    @property
    def parentheticals(self):
        return Parenthetical.objects.filter(
            described_opinion_id__in=self.sub_opinions.values_list(
                "pk", flat=True
            )
        ).order_by("-score")

    @property
    def parenthetical_groups(self):
        return ParentheticalGroup.objects.filter(
            opinion__in=self.sub_opinions.values_list("pk", flat=True)
        ).order_by("-score")

    @property
    def authority_count(self):
        return self.authorities.count()

    async def aauthority_count(self):
        authorities = await self.aauthorities()
        return await authorities.acount()

    @property
    def has_private_authority(self):
        if not hasattr(self, "_has_private_authority"):
            # Calculate it, then cache it.
            private = False
            for authority in self.authorities:
                if authority.blocked:
                    private = True
                    break
            self._has_private_authority = private
        return self._has_private_authority

    async def ahas_private_authority(self):
        if not hasattr(self, "_has_private_authority"):
            # Calculate it, then cache it.
            private = False
            async for authority in await self.aauthorities():
                if authority.blocked:
                    private = True
                    break
            self._has_private_authority = private
        return self._has_private_authority

    async def aauthorities_with_data(self):
        """Returns a list of this cluster's authorities with an extra field
        appended related to citation counts, for eventual injection into a
        view template.
        The returned list is sorted by that citation count field.
        """
        authorities_with_data = []
        authorities_base = await self.aauthorities()
        authorities_qs = (
            authorities_base.prefetch_related("citations")
            .select_related("docket__court")
            .order_by("-citation_count", "-date_filed")
        )
        async for authority in authorities_qs:
            authority.citation_depth = (
                await get_citation_depth_between_clusters(
                    citing_cluster_pk=self.pk, cited_cluster_pk=authority.pk
                )
            )
            authorities_with_data.append(authority)

        authorities_with_data.sort(
            key=lambda x: x.citation_depth, reverse=True
        )
        return authorities_with_data

    def top_visualizations(self):
        return self.visualizations.filter(
            published=True, deleted=False
        ).order_by("-view_count")

    def __str__(self) -> str:
        if self.case_name:
            return f"{self.pk}: {self.case_name}"
        else:
            return f"{self.pk}"

    def get_absolute_url(self) -> str:
        return reverse("view_case", args=[self.pk, self.slug])

    @cached_property
    def ordered_opinions(self):
        # Fetch all sub-opinions ordered by ordering_key
        sub_opinions = self.sub_opinions.all().order_by("ordering_key")

        # Check if there is more than one sub-opinion
        if sub_opinions.count() > 1:
            # Return only sub-opinions with an ordering key
            return sub_opinions.exclude(ordering_key__isnull=True)

        # If there's only one or no sub-opinions, return the main opinion
        return sub_opinions

    def save(
        self,
        update_fields=None,
        *args,
        **kwargs,
    ):
        self.slug = slugify(trunc(best_case_name(self), 75))
        if update_fields is not None:
            update_fields = {"slug"}.union(update_fields)
        super().save(update_fields=update_fields, *args, **kwargs)

    async def asave(
        self,
        update_fields=None,
        *args,
        **kwargs,
    ):
        return await sync_to_async(self.save)(
            update_fields=update_fields,
            *args,
            **kwargs,
        )


@pghistory.track(
    pghistory.InsertEvent(), pghistory.DeleteEvent(), obj_field=None
)
class OpinionClusterPanel(OpinionCluster.panel.through):
    """A model class to track opinion cluster panel m2m relation"""

    class Meta:
        proxy = True


@pghistory.track(
    pghistory.InsertEvent(), pghistory.DeleteEvent(), obj_field=None
)
class OpinionClusterNonParticipatingJudges(
    OpinionCluster.non_participating_judges.through
):
    """A model class to track opinion cluster non_participating_judges m2m
    relation"""

    class Meta:
        proxy = True


@pghistory.track()
class Citation(models.Model):
    """A simple class to hold citations."""

    FEDERAL = 1
    STATE = 2
    STATE_REGIONAL = 3
    SPECIALTY = 4
    SCOTUS_EARLY = 5
    LEXIS = 6
    WEST = 7
    NEUTRAL = 8
    JOURNAL = 9
    CITATION_TYPES = (
        (FEDERAL, "A federal reporter citation (e.g. 5 F. 55)"),
        (
            STATE,
            "A citation in a state-based reporter (e.g. Alabama Reports)",
        ),
        (
            STATE_REGIONAL,
            "A citation in a regional reporter (e.g. Atlantic Reporter)",
        ),
        (
            SPECIALTY,
            "A citation in a specialty reporter (e.g. Lawyers' Edition)",
        ),
        (
            SCOTUS_EARLY,
            "A citation in an early SCOTUS reporter (e.g. 5 Black. 55)",
        ),
        (LEXIS, "A citation in the Lexis system (e.g. 5 LEXIS 55)"),
        (WEST, "A citation in the WestLaw system (e.g. 5 WL 55)"),
        (NEUTRAL, "A vendor neutral citation (e.g. 2013 FL 1)"),
        (
            JOURNAL,
            "A law journal citation within a scholarly or professional "
            "legal periodical (e.g. 95 Yale L.J. 5; "
            "72 Soc.Sec.Rep.Serv. 318)",
        ),
    )
    cluster = models.ForeignKey(
        OpinionCluster,
        help_text="The cluster that the citation applies to",
        related_name="citations",
        on_delete=models.CASCADE,
    )
    volume = models.SmallIntegerField(help_text="The volume of the reporter")
    reporter = models.TextField(
        help_text="The abbreviation for the reporter",
        # To generate lists of volumes for a reporter we need everything in a
        # reporter. This answers, "Which volumes do we have for F. 2d?"
        db_index=True,
    )
    page = models.TextField(
        help_text=(
            "The 'page' of the citation in the reporter. Unfortunately, "
            "this is not an integer, but is a string-type because "
            "several jurisdictions do funny things with the so-called "
            "'page'. For example, we have seen Roman numerals in "
            "Nebraska, 13301-M in Connecticut, and 144M in Montana."
        ),
    )
    type = models.SmallIntegerField(
        help_text="The type of citation that this is.", choices=CITATION_TYPES
    )

    def __str__(self) -> str:
        # Note this representation is used in the front end.
        return "{volume} {reporter} {page}".format(**self.__dict__)

    def get_absolute_url(self) -> str:
        return self.cluster.get_absolute_url()

    class Meta:
        indexes = [
            # To look up individual citations
            models.Index(
                fields=["volume", "reporter", "page"],
                name="search_citation_volume_ae340b5b02e8912_idx",
            ),
            # To generate reporter volume lists
            models.Index(
                fields=["volume", "reporter"],
                name="search_citation_volume_251bc1d270a8abee_idx",
            ),
        ]
        unique_together = (("cluster", "volume", "reporter", "page"),)


def sort_cites(c):
    """Sort a list or QuerySet of citations according to BlueBook ordering.

    This is intended as a parameter to the 'key' argument of a sorting method
    like `sort` or `sorted`. It intends to take a single citation and give it a
    numeric score as to where it should occur in a list of other citations.

    For example:

        cs = Citation.objects.filter(cluser_id=222)
        cs = sorted(cs, key=sort_cites)

    That'd give you the list of the Citation items sorted by their priority.

    :param c: A Citation object to score.
    :return: A score for the Citation passed in.
    """
    if c.type == Citation.NEUTRAL:
        return 0
    if c.type == Citation.FEDERAL:
        if c.reporter == "U.S.":
            return 1.1
        elif c.reporter == "S. Ct.":
            return 1.2
        elif "L. Ed." in c.reporter:
            return 1.3
        else:
            return 1.4
    elif c.type == Citation.SCOTUS_EARLY:
        return 2
    elif c.type == Citation.SPECIALTY:
        return 3
    elif c.type == Citation.STATE_REGIONAL:
        return 4
    elif c.type == Citation.STATE:
        return 5
    elif c.type == Citation.WEST:
        return 6
    elif c.type == Citation.LEXIS:
        return 7
    else:
        return 8


@pghistory.track()
class Opinion(AbstractDateTimeModel):
    COMBINED = "010combined"
    UNANIMOUS = "015unamimous"
    LEAD = "020lead"
    PLURALITY = "025plurality"
    CONCURRENCE = "030concurrence"
    CONCUR_IN_PART = "035concurrenceinpart"
    DISSENT = "040dissent"
    ADDENDUM = "050addendum"
    REMITTUR = "060remittitur"
    REHEARING = "070rehearing"
    ON_THE_MERITS = "080onthemerits"
    ON_MOTION_TO_STRIKE = "090onmotiontostrike"
    TRIAL_COURT = "100trialcourt"
    OPINION_TYPES = (
        (COMBINED, "Combined Opinion"),
        (UNANIMOUS, "Unanimous Opinion"),
        (LEAD, "Lead Opinion"),
        (PLURALITY, "Plurality Opinion"),
        (CONCURRENCE, "Concurrence Opinion"),
        (CONCUR_IN_PART, "In Part Opinion"),
        (DISSENT, "Dissent"),
        (ADDENDUM, "Addendum"),
        (REMITTUR, "Remittitur"),
        (REHEARING, "Rehearing"),
        (ON_THE_MERITS, "On the Merits"),
        (ON_MOTION_TO_STRIKE, "On Motion to Strike Cost Bill"),
        (TRIAL_COURT, "Trial Court Document"),
    )
    cluster = models.ForeignKey(
        OpinionCluster,
        help_text="The cluster that the opinion is a part of",
        related_name="sub_opinions",
        on_delete=models.CASCADE,
    )
    opinions_cited = models.ManyToManyField(
        "self",
        help_text="Opinions cited by this opinion",
        through="OpinionsCited",
        through_fields=("citing_opinion", "cited_opinion"),
        symmetrical=False,
        related_name="opinions_citing",
        blank=True,
    )
    author = models.ForeignKey(
        "people_db.Person",
        help_text="The primary author of this opinion as a normalized field",
        related_name="opinions_written",
        on_delete=models.RESTRICT,
        blank=True,
        null=True,
    )
    author_str = models.TextField(
        help_text=(
            "The primary author of this opinion, as a simple text "
            "string. This field is used when normalized judges cannot "
            "be placed into the author field."
        ),
        blank=True,
    )
    per_curiam = models.BooleanField(
        help_text="Is this opinion per curiam, without a single author?",
        default=False,
    )
    joined_by = models.ManyToManyField(
        "people_db.Person",
        related_name="opinions_joined",
        help_text=(
            "Other judges that joined the primary author " "in this opinion"
        ),
        blank=True,
    )
    joined_by_str = models.TextField(
        help_text=(
            "Other judges that joined the primary author "
            "in this opinion str"
        ),
        blank=True,
    )
    type = models.CharField(max_length=20, choices=OPINION_TYPES)
    sha1 = models.CharField(
        help_text=(
            "unique ID for the document, as generated via SHA1 of the "
            "binary file or text data"
        ),
        max_length=40,
        db_index=True,
        blank=True,
    )
    page_count = models.IntegerField(
        help_text="The number of pages in the document, if known",
        blank=True,
        null=True,
    )
    download_url = models.URLField(
        help_text=(
            "The URL where the item was originally scraped. Note that "
            "these URLs may often be dead due to the court or the bulk "
            "provider changing their website. We keep the original link "
            "here given that it often contains valuable metadata."
        ),
        max_length=500,
        db_index=True,
        null=True,
        blank=True,
    )
    local_path = models.FileField(
        help_text=(
            "The location in AWS S3 where the original opinion file is "
            f"stored. {s3_warning_note}"
        ),
        upload_to=make_upload_path,
        storage=IncrementingAWSMediaStorage(),
        blank=True,
        db_index=True,
    )
    plain_text = models.TextField(
        help_text=(
            "Plain text of the document after extraction using "
            "pdftotext, wpd2txt, etc."
        ),
        blank=True,
    )
    html = models.TextField(
        help_text="HTML of the document, if available in the original",
        blank=True,
    )
    html_lawbox = models.TextField(
        help_text="HTML of Lawbox documents", blank=True
    )
    html_columbia = models.TextField(
        help_text="HTML of Columbia archive", blank=True
    )
    html_anon_2020 = models.TextField(
        help_text="HTML of 2020 anonymous archive",
        blank=True,
    )
    xml_harvard = models.TextField(
        help_text="XML of Harvard CaseLaw Access Project opinion", blank=True
    )
    html_with_citations = models.TextField(
        help_text=(
            "HTML of the document with citation links and other "
            "post-processed markup added"
        ),
        blank=True,
    )
    extracted_by_ocr = models.BooleanField(
        help_text="Whether OCR was used to get this document content",
        default=False,
        db_index=True,
    )
    es_pa_field_tracker = FieldTracker(
        fields=["extracted_by_ocr", "cluster_id", "author_id"]
    )
    es_o_field_tracker = FieldTracker(
        fields=[
            "cluster_id",
            "author_id",
            "type",
            "per_curiam",
            "download_url",
            "local_path",
            "html_columbia",
            "html_lawbox",
            "xml_harvard",
            "html_anon_2020",
            "html",
            "plain_text",
            "sha1",
        ]
    )
    ordering_key = models.IntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["cluster_id", "ordering_key"],
                name="unique_opinion_ordering_key",
            )
        ]

    @property
    def siblings(self) -> QuerySet:
        # These are other sub-opinions of the current cluster.
        return self.cluster.sub_opinions

    def __str__(self) -> str:
        try:
            return f"{getattr(self, 'pk', None)} - {self.cluster.case_name}"
        except AttributeError:
            return f"Orphan opinion with ID: {self.pk}"

    def get_absolute_url(self) -> str:
        return reverse("view_case", args=[self.cluster.pk, self.cluster.slug])

    def clean(self) -> None:
        if self.type == "":
            raise ValidationError("'type' is a required field.")
        if isinstance(self.ordering_key, int) and self.ordering_key < 1:
            raise ValidationError(
                {"ordering_key": "Ordering key cannot be zero or negative"}
            )

    def save(
        self,
        *args: List,
        **kwargs: Dict,
    ) -> None:
        self.clean()
        super().save(*args, **kwargs)


@pghistory.track(
    pghistory.InsertEvent(), pghistory.DeleteEvent(), obj_field=None
)
class OpinionJoinedBy(Opinion.joined_by.through):
    """A model class to track opinion joined_by m2m relation"""

    class Meta:
        proxy = True


class OpinionsCited(models.Model):
    citing_opinion = models.ForeignKey(
        Opinion, related_name="cited_opinions", on_delete=models.CASCADE
    )
    cited_opinion = models.ForeignKey(
        Opinion, related_name="citing_opinions", on_delete=models.CASCADE
    )
    depth = models.IntegerField(
        help_text="The number of times the cited opinion was cited "
        "in the citing opinion",
        default=1,
        db_index=True,
    )

    #  quoted = models.BooleanField(
    #      help_text='Equals true if previous case was quoted directly',
    #      default=False,
    #      db_index=True,
    #  )
    # treatment: positive, negative, etc.
    #

    def __str__(self) -> str:
        return f"{self.citing_opinion.id} ⤜--cites⟶  {self.cited_opinion.id}"

    class Meta:
        verbose_name_plural = "Opinions cited"
        unique_together = ("citing_opinion", "cited_opinion")


class OpinionsCitedByRECAPDocument(models.Model):
    citing_document = models.ForeignKey(
        RECAPDocument, related_name="cited_opinions", on_delete=models.CASCADE
    )
    cited_opinion = models.ForeignKey(
        Opinion, related_name="citing_documents", on_delete=models.CASCADE
    )
    depth = models.IntegerField(
        help_text="The number of times the cited opinion was cited "
        "in the citing document",
        default=1,
    )

    def __str__(self) -> str:
        return f"{self.citing_document.id} ⤜--cites⟶  {self.cited_opinion.id}"

    class Meta:
        verbose_name_plural = "Opinions cited by RECAP document"
        unique_together = ("citing_document", "cited_opinion")
        indexes = [models.Index(fields=["depth"])]


def build_authorities_query(
    base_queryset: QuerySet[OpinionsCitedByRECAPDocument],
) -> QuerySet[OpinionsCitedByRECAPDocument]:
    """
    Optimizes the authorities query by applying select_related, prefetch_related,
    and selecting only the relevant fields to display the list of citations

    Args:
        base_queryset (QuerySet[OpinionsCitedByRECAPDocument]): The queryset to optimize
    """
    return (
        base_queryset.select_related("cited_opinion__cluster__docket__court")
        .prefetch_related(
            "cited_opinion__cluster__citations",
        )
        .only(
            "depth",
            "citing_document_id",
            "cited_opinion__cluster__slug",
            "cited_opinion__cluster__case_name",
            "cited_opinion__cluster__case_name_full",
            "cited_opinion__cluster__case_name_short",
            "cited_opinion__cluster__citation_count",
            "cited_opinion__cluster__docket_id",
            "cited_opinion__cluster__date_filed",
            "cited_opinion__cluster__docket__docket_number",
            "cited_opinion__cluster__docket__court_id",
            "cited_opinion__cluster__docket__court__citation_string",
            "cited_opinion__cluster__docket__court__full_name",
        )
        .order_by("-depth")
    )


class Parenthetical(models.Model):
    describing_opinion = models.ForeignKey(
        Opinion,
        related_name="authored_parentheticals",
        on_delete=models.CASCADE,
    )
    described_opinion = models.ForeignKey(
        Opinion, related_name="parentheticals", on_delete=models.CASCADE
    )
    group = models.ForeignKey(
        "ParentheticalGroup",
        related_name="parentheticals",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    text = models.TextField(
        help_text="The text of the description as written in the describing "
        "opinion",
    )
    score = models.FloatField(
        db_index=True,
        default=0.0,
        help_text="A score between 0 and 1 representing how descriptive the "
        "parenthetical is",
    )
    es_pa_field_tracker = FieldTracker(fields=["score", "text"])

    def __str__(self) -> str:
        return (
            f"{self.describing_opinion.id} description of "
            f"{self.described_opinion.id} (score {self.score}): {self.text}"
        )

    def get_absolute_url(self) -> str:
        cluster = self.described_opinion.cluster
        return reverse("view_summaries", args=[cluster.pk, cluster.slug])

    class Meta:
        verbose_name_plural = "Opinion parentheticals"


class ParentheticalGroup(models.Model):
    opinion = models.ForeignKey(
        Opinion,
        related_name="parenthetical_groups",
        on_delete=models.CASCADE,
        help_text="The opinion that the parentheticals in the group describe",
    )
    representative = models.ForeignKey(
        Parenthetical,
        related_name="represented_group",
        on_delete=models.CASCADE,
        help_text="The representative (i.e. high-ranked and similar to the "
        "cluster as a whole) parenthetical for the group",
    )
    score = models.FloatField(
        default=0.0,
        help_text="A score between 0 and 1 representing the quality of the "
        "parenthetical group",
    )
    size = models.IntegerField(
        help_text="The number of parentheticals that belong to the group"
    )

    es_pa_field_tracker = FieldTracker(
        fields=["opinion_id", "representative_id"]
    )

    def __str__(self) -> str:
        return (
            f"Parenthetical group for opinion {self.opinion_id} "
            f"(score {self.score})"
        )

    def get_absolute_url(self) -> str:
        return self.representative.get_absolute_url()

    class Meta:
        verbose_name_plural = "Parenthetical groups"
        indexes = [models.Index(fields=["score"])]


TaggableType = TypeVar("TaggableType", Docket, DocketEntry, RECAPDocument)


@pghistory.track()
class Tag(AbstractDateTimeModel):
    name = models.CharField(
        help_text="The name of the tag.",
        max_length=50,
        db_index=True,
        unique=True,
    )

    def __str__(self) -> str:
        return f"{self.pk}: {self.name}"

    def tag_object(self, thing: TaggableType) -> Tuple["Tag", bool]:
        """Atomically add a tag to an item.

        Django has a system for adding to a m2m relationship like the ones
        between tags and other objects. Normally, you can just use:

            some_thing.add(tag)

        Alas, that's not atomic and if you have multiple processes or threads
        running — as you would in a Celery queue — you will get
        IntegrityErrors. So...this function does the same thing by using the
        tag through tables, as described here:

            https://stackoverflow.com/a/37968648/64911

        By using get_or_create calls, we make it atomic, fixing the problem.

        :param thing: Either a Docket, DocketEntry, or RECAPDocument that you
        wish to tag.
        :return: A tuple with the tag and whether a new item was created
        """
        if type(thing) == Docket:
            return self.dockets.through.objects.get_or_create(
                docket_id=thing.pk, tag_id=self.pk
            )
        elif type(thing) == DocketEntry:
            return self.docket_entries.through.objects.get_or_create(
                docketentry_id=thing.pk, tag_id=self.pk
            )
        elif type(thing) == RECAPDocument:
            return self.recap_documents.through.objects.get_or_create(
                recapdocument_id=thing.pk, tag_id=self.pk
            )
        elif type(thing) == Claim:
            return self.claims.through.objects.get_or_create(
                claim_id=thing.pk, tag_id=self.pk
            )
        else:
            raise NotImplementedError("Object type not supported for tagging.")


# class AppellateReview(models.Model):
#     REVIEW_STANDARDS = (
#         ('d', 'Discretionary'),
#         ('m', 'Mandatory'),
#         ('s', 'Special or Mixed'),
#     )
#     upper_court = models.ForeignKey(
#         Court,
#         related_name='lower_courts_reviewed',
#         on_delete=models.RESTRICT,
#     )
#     lower_court = models.ForeignKey(
#         Court,
#         related_name='reviewed_by',
#         on_delete=models.RESTRICT,
#     )
#     date_start = models.DateTimeField(
#         help_text="The date this appellate review relationship began",
#         db_index=True,
#         null=True
#     )
#     date_end = models.DateTimeField(
#         help_text="The date this appellate review relationship ended",
#         db_index=True,
#         null=True
#     )
#     review_standard =  models.CharField(
#         max_length=1,
#         choices=REVIEW_STANDARDS,
#     )
#     def __str__(self) -> str:
#         return u'%s ⤜--reviewed by⟶  %s' % (self.lower_court.id,
#                                         self.upper_court.id)
#
#     class Meta:
#         unique_together = ("upper_court", "lower_court")
class SEARCH_TYPES:
    OPINION = "o"
    RECAP = "r"
    DOCKETS = "d"
    RECAP_DOCUMENT = "rd"
    ORAL_ARGUMENT = "oa"
    PEOPLE = "p"
    PARENTHETICAL = "pa"
    NAMES = (
        (OPINION, "Opinions"),
        (RECAP, "RECAP"),
        (DOCKETS, "RECAP Dockets"),
        (RECAP_DOCUMENT, "RECAP Documents"),
        (ORAL_ARGUMENT, "Oral Arguments"),
        (PEOPLE, "People"),
        (PARENTHETICAL, "Parenthetical"),
    )
    ALL_TYPES = [OPINION, RECAP, ORAL_ARGUMENT, PEOPLE]
    SUPPORTED_ALERT_TYPES = (
        (OPINION, "Opinions"),
        (RECAP, "RECAP"),
        (ORAL_ARGUMENT, "Oral Arguments"),
    )


class SearchQuery(models.Model):
    WEBSITE = 1
    API = 2
    SOURCES = (
        (WEBSITE, "Website"),
        (API, "API request"),
    )
    ELASTICSEARCH = 1
    SOLR = 2
    ENGINES = (
        (ELASTICSEARCH, "Elasticsearch"),
        (SOLR, "Solr"),
    )
    user = models.ForeignKey(
        User,
        help_text="The user who performed this search query.",
        related_name="search_queries",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    source = models.SmallIntegerField(
        help_text="The interface used to perform the query.", choices=SOURCES
    )
    get_params = models.TextField(
        help_text="The GET parameters of the search query."
    )
    query_time_ms = models.IntegerField(
        help_text="The milliseconds to execute the query, as returned in "
        "the ElasticSearch or Solr response.",
        null=True,
    )
    hit_cache = models.BooleanField(
        help_text="Whether the query hit the cache or not."
    )
    failed = models.BooleanField(
        help_text="True if there was an error executing the query."
    )
    engine = models.SmallIntegerField(
        help_text="The engine that executed the search", choices=ENGINES
    )
    date_created = models.DateTimeField(
        help_text="Datetime when the record was created.",
        auto_now_add=True,
    )

    class Meta:
        indexes = [
            models.Index(fields=["date_created"]),
        ]
