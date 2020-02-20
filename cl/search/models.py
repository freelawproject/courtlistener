# coding=utf-8
import os
import re

from celery.canvas import chain
from django.contrib.contenttypes.fields import GenericRelation
from django.core.exceptions import ValidationError
from django.urls import reverse, NoReverseMatch
from django.db import models
from django.db.models import Prefetch, Q
from django.template import loader
from django.utils.encoding import smart_unicode
from django.utils.text import slugify

from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.lib import fields
from cl.lib.date_time import midnight_pst
from cl.lib.model_helpers import (
    make_upload_path,
    make_recap_path,
    make_docket_number_core,
)
from cl.lib.models import AbstractPDF
from cl.lib.search_index_utils import (
    InvalidDocumentError,
    null_map,
    normalize_search_dicts,
)
from cl.lib.storage import IncrementingFileSystemStorage
from cl.lib.string_utils import trunc
from cl.citations.utils import get_citation_depth_between_clusters

DOCUMENT_STATUSES = (
    ("Published", "Precedential"),
    ("Unpublished", "Non-Precedential"),
    ("Errata", "Errata"),
    ("Separate", "Separate Opinion"),
    ("In-chambers", "In-chambers"),
    ("Relating-to", "Relating-to orders"),
    ("Unknown", "Unknown Status"),
)

SOURCES = (
    ("C", "court website"),
    ("R", "public.resource.org"),
    ("CR", "court website merged with resource.org"),
    ("L", "lawbox"),
    ("LC", "lawbox merged with court"),
    ("LR", "lawbox merged with resource.org"),
    ("LCR", "lawbox merged with court and resource.org"),
    ("M", "manual input"),
    ("A", "internet archive"),
    ("H", "brad heath archive"),
    ("Z", "columbia archive"),
    ("ZC", "columbia merged with court"),
    ("ZLC", "columbia merged with lawbox and court"),
    ("ZLR", "columbia merged with lawbox and resource.org"),
    ("ZLCR", "columbia merged with lawbox, court, and resource.org"),
    ("ZR", "columbia merged with resource.org"),
    ("ZCR", "columbia merged with court and resource.org"),
    ("ZL", "columbia merged with lawbox"),
    ("U", "Harvard, Library Innovation Lab Case Law Access Project"),
    ("CU", "court website merged with Harvard"),
)


class OriginatingCourtInformation(models.Model):
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
    docket_number = models.TextField(
        help_text="The docket number in the lower court.", blank=True,
    )
    assigned_to = models.ForeignKey(
        "people_db.Person",
        help_text="The judge the case was assigned to.",
        related_name="original_court_info",
        on_delete=models.CASCADE,
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
        on_delete=models.CASCADE,
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
        help_text="The court reporter responsible for the case.", blank=True,
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

    def __unicode__(self):
        return "<OriginatingCourtInformation: %s>" % self.pk

    def get_absolute_url(self):
        return self.docket.get_absolute_url()

    class Meta:
        verbose_name_plural = "Originating Court Information"


class Docket(models.Model):
    """A class to sit above OpinionClusters, Audio files, and Docket Entries,
    and link them together.
    """

    # The source values are additive. That is, if you get content from a new
    # source, you can add it to the previous one, and have a combined value.
    # For example, if you start with a RECAP docket (1), then add scraped
    # content (2), you can arrive at a combined docket (3) because 1 + 2 = 3.
    DEFAULT = 0
    RECAP = 1
    SCRAPER = 2
    RECAP_AND_SCRAPER = 3
    COLUMBIA = 4
    COLUMBIA_AND_RECAP = 5
    COLUMBIA_AND_SCRAPER = 6
    COLUMBIA_AND_RECAP_AND_SCRAPER = 7
    IDB = 8
    RECAP_AND_IDB = 9
    SCRAPER_AND_IDB = 10
    RECAP_AND_SCRAPER_AND_IDB = 11
    COLUMBIA_AND_IDB = 12
    COLUMBIA_AND_RECAP_AND_IDB = 13
    COLUMBIA_AND_SCRAPER_AND_IDB = 14
    COLUMBIA_AND_RECAP_AND_SCRAPER_AND_IDB = 15
    HARVARD = 16
    SCRAPER_AND_HARVARD = 17
    SOURCE_CHOICES = (
        (DEFAULT, "Default"),
        (RECAP, "RECAP"),
        (SCRAPER, "Scraper"),
        (RECAP_AND_SCRAPER, "RECAP and Scraper"),
        (COLUMBIA, "Columbia"),
        (COLUMBIA_AND_SCRAPER, "Columbia and Scraper"),
        (COLUMBIA_AND_RECAP, "Columbia and RECAP"),
        (COLUMBIA_AND_RECAP_AND_SCRAPER, "Columbia, RECAP, and Scraper"),
        (IDB, "Integrated Database"),
        (RECAP_AND_IDB, "RECAP and IDB"),
        (SCRAPER_AND_IDB, "Scraper and IDB"),
        (RECAP_AND_SCRAPER_AND_IDB, "RECAP, Scraper, and IDB"),
        (COLUMBIA_AND_IDB, "Columbia and IDB"),
        (COLUMBIA_AND_RECAP_AND_IDB, "Columbia, RECAP, and IDB"),
        (COLUMBIA_AND_SCRAPER_AND_IDB, "Columbia, Scraper, and IDB"),
        (
            COLUMBIA_AND_RECAP_AND_SCRAPER_AND_IDB,
            "Columbia, RECAP, Scraper, and IDB",
        ),
        (HARVARD, "Harvard"),
        (SCRAPER_AND_HARVARD, "Scraper and Harvard"),
    )
    RECAP_SOURCES = [
        RECAP,
        RECAP_AND_SCRAPER,
        COLUMBIA_AND_RECAP,
        COLUMBIA_AND_RECAP_AND_SCRAPER,
        RECAP_AND_IDB,
        RECAP_AND_SCRAPER_AND_IDB,
        COLUMBIA_AND_RECAP_AND_IDB,
        COLUMBIA_AND_RECAP_AND_SCRAPER_AND_IDB,
    ]
    IDB_SOURCES = [
        IDB,
        RECAP_AND_IDB,
        SCRAPER_AND_IDB,
        RECAP_AND_SCRAPER_AND_IDB,
        COLUMBIA_AND_IDB,
        COLUMBIA_AND_RECAP_AND_IDB,
        COLUMBIA_AND_SCRAPER_AND_IDB,
        COLUMBIA_AND_RECAP_AND_SCRAPER_AND_IDB,
    ]

    source = models.SmallIntegerField(
        help_text="contains the source of the Docket.", choices=SOURCE_CHOICES,
    )
    court = models.ForeignKey(
        "Court",
        help_text="The court where the docket was filed",
        on_delete=models.CASCADE,
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
        on_delete=models.CASCADE,
        blank=True,
        null=True,
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
        on_delete=models.CASCADE,
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
        on_delete=models.CASCADE,
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
        on_delete=models.CASCADE,
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
        on_delete=models.CASCADE,
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
    date_created = models.DateTimeField(
        help_text="The time when this item was created",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text=(
            "The last moment when the item was modified. A value in "
            "year 1750 indicates the value is unknown"
        ),
        auto_now=True,
        db_index=True,
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
        db_index=True,
    )
    date_cert_denied = models.DateField(
        help_text="the date cert was denied for this case, if applicable",
        blank=True,
        null=True,
        db_index=True,
    )
    date_argued = models.DateField(
        help_text="the date the case was argued",
        blank=True,
        null=True,
        db_index=True,
    )
    date_reargued = models.DateField(
        help_text="the date the case was reargued",
        blank=True,
        null=True,
        db_index=True,
    )
    date_reargument_denied = models.DateField(
        help_text="the date the reargument was denied",
        blank=True,
        null=True,
        db_index=True,
    )
    date_filed = models.DateField(
        help_text="The date the case was filed.", blank=True, null=True,
    )
    date_terminated = models.DateField(
        help_text="The date the case was terminated.", blank=True, null=True,
    )
    date_last_filing = models.DateField(
        help_text=(
            "The date the case was last updated in the docket, as shown "
            "in PACER's Docket History report."
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
        help_text="The standard name of the case", blank=True,
    )
    case_name_full = models.TextField(
        help_text="The full name of the case", blank=True,
    )
    slug = models.SlugField(
        help_text="URL that the document should map to (the slug)",
        max_length=75,
        db_index=False,
        blank=True,
    )
    docket_number = models.TextField(
        help_text="The docket numbers of a case, can be consolidated and "
        "quite long",
        blank=True,
        null=True,
        db_index=True,
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
    # Nullable for unique constraint requirements.
    pacer_case_id = fields.CharNullField(
        help_text="The cased ID provided by PACER.",
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
        help_text="The compensation demand.", max_length=500, blank=True,
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
        help_text="Path to RECAP's Docket XML page.",
        upload_to=make_recap_path,
        storage=IncrementingFileSystemStorage(),
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
    ia_needs_upload = models.NullBooleanField(
        help_text=(
            "Does this item need to be uploaded to the Internet "
            "Archive? I.e., has it changed? This field is important "
            "because it keeps track of the status of all the related "
            "objects to the docket. For example, if a related docket "
            "entry changes, we need to upload the item to IA, but we "
            "can't easily check that."
        ),
        blank=True,
        db_index=True,
    )
    ia_date_first_change = models.DateTimeField(
        help_text=(
            "The moment when this item first changed and was marked as "
            "needing an upload. Used for determining when to upload an "
            "item."
        ),
        null=True,
        blank=True,
        db_index=True,
    )
    view_count = models.IntegerField(
        help_text="The number of times the docket has been seen.", default=0,
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

    class Meta:
        unique_together = ("docket_number", "pacer_case_id", "court")
        index_together = (
            (
                "ia_upload_failure_count",
                "ia_needs_upload",
                "ia_date_first_change",
            ),
        )

    def __unicode__(self):
        if self.case_name:
            return smart_unicode("%s: %s" % (self.pk, self.case_name))
        else:
            return u"{pk}".format(pk=self.pk)

    def save(self, *args, **kwargs):
        self.slug = slugify(trunc(best_case_name(self), 75))
        if self.docket_number and not self.docket_number_core:
            self.docket_number_core = make_docket_number_core(
                self.docket_number
            )
        if self.source in self.RECAP_SOURCES:
            for field in ["pacer_case_id", "docket_number"]:
                if not getattr(self, field, None):
                    raise ValidationError(
                        "'%s' cannot be Null or empty in "
                        "RECAP dockets." % field
                    )

        super(Docket, self).save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("view_docket", args=[self.pk, self.slug])

    def add_recap_source(self):
        if self.source == self.DEFAULT:
            self.source = self.RECAP_AND_SCRAPER
        elif self.source in [
            self.SCRAPER,
            self.COLUMBIA,
            self.COLUMBIA_AND_SCRAPER,
            self.IDB,
            self.SCRAPER_AND_IDB,
            self.COLUMBIA_AND_IDB,
            self.COLUMBIA_AND_SCRAPER_AND_IDB,
        ]:
            # Simply add the RECAP value to the other value.
            self.source = self.source + self.RECAP

    def add_idb_source(self):
        if self.source == self.DEFAULT:
            self.source = self.IDB
        elif self.source in [
            self.RECAP,
            self.SCRAPER,
            self.RECAP_AND_SCRAPER,
            self.COLUMBIA,
            self.COLUMBIA_AND_RECAP,
            self.COLUMBIA_AND_SCRAPER,
            self.COLUMBIA_AND_RECAP_AND_SCRAPER,
        ]:
            self.source = self.source + self.IDB

    @property
    def pacer_url(self):
        if not self.pacer_case_id:
            return None
        from cl.lib.pacer import map_cl_to_pacer_id

        court_id = map_cl_to_pacer_id(self.court.pk)
        if self.court.jurisdiction == Court.FEDERAL_APPELLATE:
            if self.court.pk in ["ca5", "ca7", "ca11"]:
                path = "/cmecf/servlet/TransportRoom?"
            else:
                path = "/n/beam/servlet/TransportRoom?"

            return (
                u"https://ecf.%s.uscourts.gov"
                + path
                + u"servlet=CaseSummary.jsp&"
                u"caseNum=%s&"
                u"incOrigDkt=Y&"
                u"incDktEntries=Y"
            ) % (court_id, self.pacer_case_id,)
        else:
            return u"https://ecf.%s.uscourts.gov/cgi-bin/DktRpt.pl?%s" % (
                court_id,
                self.pacer_case_id,
            )

    @property
    def prefetched_parties(self):
        """Prefetch the attorneys and firms associated with a docket and put
        those values into the `attys_in_docket` and `firms_in_docket`
        attributes.

        :return: A parties queryset with the correct values prefetched.
        """
        from cl.people_db.models import Attorney, AttorneyOrganization

        return self.parties.prefetch_related(
            Prefetch(
                "attorneys",
                queryset=Attorney.objects.filter(roles__docket=self)
                .distinct()
                .only("pk", "name"),
                to_attr="attys_in_docket",
            ),
            Prefetch(
                "attys_in_docket__organizations",
                queryset=AttorneyOrganization.objects.filter(
                    attorney_organization_associations__docket=self
                )
                .distinct()
                .only("pk", "name"),
                to_attr="firms_in_docket",
            ),
        )

    def as_search_list(self):
        """Create list of search dicts from a single docket. This should be
        faster than creating a search dict per document on the docket.
        """
        search_list = []

        # Docket
        out = {
            "docketNumber": self.docket_number,
            "caseName": best_case_name(self),
            "suitNature": self.nature_of_suit,
            "cause": self.cause,
            "juryDemand": self.jury_demand,
            "jurisdictionType": self.jurisdiction_type,
        }
        if self.date_argued is not None:
            out["dateArgued"] = midnight_pst(self.date_argued)
        if self.date_filed is not None:
            out["dateFiled"] = midnight_pst(self.date_filed)
        if self.date_terminated is not None:
            out["dateTerminated"] = midnight_pst(self.date_terminated)
        try:
            out["docket_absolute_url"] = self.get_absolute_url()
        except NoReverseMatch:
            raise InvalidDocumentError(
                "Unable to save to index due to "
                "missing absolute_url: %s" % self.pk
            )

        # Judges
        if self.assigned_to is not None:
            out["assignedTo"] = self.assigned_to.name_full
        elif self.assigned_to_str:
            out["assignedTo"] = self.assigned_to_str
        if self.referred_to is not None:
            out["referredTo"] = self.referred_to.name_full
        elif self.referred_to_str:
            out["referredTo"] = self.referred_to_str

        # Court
        out.update(
            {
                "court": self.court.full_name,
                "court_exact": self.court_id,  # For faceting
                "court_citation_string": self.court.citation_string,
            }
        )

        # Parties, attorneys, firms
        out.update(
            {
                "party_id": set(),
                "party": set(),
                "attorney_id": set(),
                "attorney": set(),
                "firm_id": set(),
                "firm": set(),
            }
        )
        for p in self.prefetched_parties:
            out["party_id"].add(p.pk)
            out["party"].add(p.name)
            for a in p.attys_in_docket:
                out["attorney_id"].add(a.pk)
                out["attorney"].add(a.name)
                for f in a.firms_in_docket:
                    out["firm_id"].add(f.pk)
                    out["firm"].add(f.name)

        # Do RECAPDocument and Docket Entries in a nested loop
        for de in self.docket_entries.all():
            # Docket Entry
            de_out = {
                "description": de.description,
            }
            if de.entry_number is not None:
                de_out["entry_number"] = de.entry_number
            if de.date_filed is not None:
                de_out["entry_date_filed"] = midnight_pst(de.date_filed)
            rds = de.recap_documents.all()

            if len(rds) == 0:
                # Minute entry or other entry that lacks docs.
                # For now, we punt.
                # https://github.com/freelawproject/courtlistener/issues/784
                continue

            for rd in rds:
                # IDs
                rd_out = {
                    "id": rd.pk,
                    "docket_entry_id": de.pk,
                    "docket_id": self.pk,
                    "court_id": self.court.pk,
                    "assigned_to_id": getattr(self.assigned_to, "pk", None),
                    "referred_to_id": getattr(self.referred_to, "pk", None),
                }

                # RECAPDocument
                rd_out.update(
                    {
                        "short_description": rd.description,
                        "document_type": rd.get_document_type_display(),
                        "document_number": rd.document_number or None,
                        "attachment_number": rd.attachment_number,
                        "is_available": rd.is_available,
                        "page_count": rd.page_count,
                    }
                )
                if hasattr(rd.filepath_local, "path"):
                    rd_out["filepath_local"] = rd.filepath_local.path
                try:
                    rd_out["absolute_url"] = rd.get_absolute_url()
                except NoReverseMatch:
                    raise InvalidDocumentError(
                        "Unable to save to index due to missing absolute_url: "
                        "%s" % self.pk
                    )

                text_template = loader.get_template("indexes/dockets_text.txt")
                rd_out["text"] = text_template.render({"item": rd}).translate(
                    null_map
                )

                # Ensure that loops to bleed into each other
                out_copy = out.copy()
                out_copy.update(rd_out)
                out_copy.update(rd_out)

                search_list.append(normalize_search_dicts(out_copy))

        return search_list

    def reprocess_recap_content(self, do_original_xml=False):
        """Go over any associated RECAP files and reprocess them.

        Start with the XML, then do them in the order they were received since
        that should correspond to the history of the docket itself.

        :param do_original_xml: Whether to do the original XML file as received
        from Internet Archive.
        """
        if self.source not in self.RECAP_SOURCES:
            return

        from cl.lib.pacer import process_docket_data

        # Start with the XML if we've got it.
        if do_original_xml and self.filepath_local:
            from cl.recap.models import UPLOAD_TYPE

            process_docket_data(
                self, self.filepath_local.path, UPLOAD_TYPE.IA_XML_FILE
            )

        # Then layer the uploads on top of that.
        for html in self.html_documents.order_by("date_created"):
            process_docket_data(self, html.filepath.path, html.upload_type)


class DocketEntry(models.Model):

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
    date_created = models.DateTimeField(
        help_text="The time when this item was created.",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified.",
        auto_now=True,
        db_index=True,
    )
    date_filed = models.DateField(
        help_text="The created date of the Docket Entry.",
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
        db_index=True,
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
        db_index=True,
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

    class Meta:
        verbose_name_plural = "Docket Entries"
        index_together = ("recap_sequence_number", "entry_number")
        ordering = ("recap_sequence_number", "entry_number")
        permissions = (("has_recap_api_access", "Can work with RECAP API"),)

    def __unicode__(self):
        return "<DocketEntry:%s ---> %s >" % (
            self.pk,
            trunc(self.description, 50, ellipsis="..."),
        )


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
        help_text=(
            "The ID of the document in PACER. This information is "
            "provided by RECAP."
        ),
        max_length=32,  # Same as in RECAP
        blank=True,
    )
    is_available = models.NullBooleanField(
        help_text="True if the item is available in RECAP",
        blank=True,
        null=True,
        default=False,
    )
    is_free_on_pacer = models.NullBooleanField(
        help_text="Is this item freely available as an opinion on PACER?",
        db_index=True,
    )
    is_sealed = models.NullBooleanField(
        help_text="Is this item sealed or otherwise unavailable on PACER?",
        db_index=True,
    )

    class Meta:
        abstract = True


class RECAPDocument(AbstractPacerDocument, AbstractPDF):
    """
        The model for Docket Documents and Attachments.
    """

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
        db_index=True,
        choices=DOCUMENT_TYPES,
    )
    description = models.TextField(
        help_text=(
            "The short description of the docket entry that appears on "
            "the attachments page."
        ),
        blank=True,
    )

    class Meta:
        unique_together = (
            "docket_entry",
            "document_number",
            "attachment_number",
        )
        ordering = ("document_type", "document_number", "attachment_number")
        index_together = [
            ["document_type", "document_number", "attachment_number"],
        ]
        permissions = (("has_recap_api_access", "Can work with RECAP API"),)

    def __unicode__(self):
        return "%s: Docket_%s , document_number_%s , attachment_number_%s" % (
            self.pk,
            self.docket_entry.docket.docket_number,
            self.document_number,
            self.attachment_number,
        )

    def get_absolute_url(self):
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

    @property
    def pacer_url(self):
        """Construct a doc1 URL for any item, if we can. Else, return None."""
        from cl.lib.pacer import map_cl_to_pacer_id

        court = self.docket_entry.docket.court
        court_id = map_cl_to_pacer_id(court.pk)
        if self.pacer_doc_id:
            if court.jurisdiction == Court.FEDERAL_APPELLATE:
                path = "docs1"
            else:
                path = "doc1"
            return "https://ecf.%s.uscourts.gov/%s/%s?caseid=%s" % (
                court_id,
                path,
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
    def needs_extraction(self):
        """Does the item need extraction and does it have all the right
        fields? Items needing OCR still need extraction.
        """
        return all(
            [
                self.ocr_status is None or self.ocr_status == self.OCR_NEEDED,
                self.is_available is True,
                # Has a value in filepath field, which points to a file.
                self.filepath_local
                and os.path.isfile(self.filepath_local.path),
            ]
        )

    def save(self, do_extraction=False, index=False, *args, **kwargs):
        if self.document_type == self.ATTACHMENT:
            if self.attachment_number is None:
                raise ValidationError(
                    "attachment_number cannot be null for an attachment."
                )

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

        super(RECAPDocument, self).save(*args, **kwargs)
        tasks = []
        if do_extraction and self.needs_extraction:
            # Context extraction not done and is requested.
            from cl.scrapers.tasks import extract_recap_pdf

            tasks.append(extract_recap_pdf.si(self.pk))
        if index:
            from cl.search.tasks import add_items_to_solr

            tasks.append(
                add_items_to_solr.si([self.pk], "search.RECAPDocument")
            )
        if len(tasks) > 0:
            chain(*tasks)()

    def delete(self, *args, **kwargs):
        """
        Note that this doesn't get called when an entire queryset
        is deleted, but that should be OK.
        """
        id_cache = self.pk
        super(RECAPDocument, self).delete(*args, **kwargs)
        from cl.search.tasks import delete_items

        delete_items.delay([id_cache], "search.RECAPDocument")

    def get_docket_metadata(self):
        """The metadata for the item that comes from the Docket."""
        docket = self.docket_entry.docket
        # IDs
        out = {
            "docket_id": docket.pk,
            "court_id": docket.court.pk,
            "assigned_to_id": getattr(docket.assigned_to, "pk", None),
            "referred_to_id": getattr(docket.referred_to, "pk", None),
        }

        # Docket
        out.update(
            {
                "docketNumber": docket.docket_number,
                "caseName": best_case_name(docket),
                "suitNature": docket.nature_of_suit,
                "cause": docket.cause,
                "juryDemand": docket.jury_demand,
                "jurisdictionType": docket.jurisdiction_type,
            }
        )
        if docket.date_argued is not None:
            out["dateArgued"] = midnight_pst(docket.date_argued)
        if docket.date_filed is not None:
            out["dateFiled"] = midnight_pst(docket.date_filed)
        if docket.date_terminated is not None:
            out["dateTerminated"] = midnight_pst(docket.date_terminated)
        try:
            out["docket_absolute_url"] = docket.get_absolute_url()
        except NoReverseMatch:
            raise InvalidDocumentError(
                "Unable to save to index due to missing absolute_url: %s"
                % self.pk
            )

        # Judges
        if docket.assigned_to is not None:
            out["assignedTo"] = docket.assigned_to.name_full
        elif docket.assigned_to_str:
            out["assignedTo"] = docket.assigned_to_str
        if docket.referred_to is not None:
            out["referredTo"] = docket.referred_to.name_full
        elif docket.referred_to_str:
            out["referredTo"] = docket.referred_to_str

        # Court
        out.update(
            {
                "court": docket.court.full_name,
                "court_exact": docket.court_id,  # For faceting
                "court_citation_string": docket.court.citation_string,
            }
        )

        # Parties, Attorneys, Firms
        out.update(
            {
                "party_id": set(),
                "party": set(),
                "attorney_id": set(),
                "attorney": set(),
                "firm_id": set(),
                "firm": set(),
            }
        )
        for p in docket.prefetched_parties:
            out["party_id"].add(p.pk)
            out["party"].add(p.name)
            for a in p.attys_in_docket:
                out["attorney_id"].add(a.pk)
                out["attorney"].add(a.name)
                for f in a.firms_in_docket:
                    out["firm_id"].add(f.pk)
                    out["firm"].add(f.name)

        return out

    def as_search_dict(self, docket_metadata=None):
        """Create a dict that can be ingested by Solr.

        Search results are presented as Dockets, but they're indexed as
        RECAPDocument's, which are then grouped back together in search results
        to form Dockets.

        Since it's common to update an entire docket, there's a shortcut,
        get_docket_metadata that lets you query that information first and then
        pass it in as an argument so that it doesn't have to be queried for
        every RECAPDocument on the docket. This can provide big performance
        boosts.
        """
        out = docket_metadata or self.get_docket_metadata()

        # IDs
        out.update(
            {"id": self.pk, "docket_entry_id": self.docket_entry.pk,}
        )

        # RECAPDocument
        out.update(
            {
                "short_description": self.description,
                "document_type": self.get_document_type_display(),
                "document_number": self.document_number or None,
                "attachment_number": self.attachment_number,
                "is_available": self.is_available,
                "page_count": self.page_count,
            }
        )
        if hasattr(self.filepath_local, "path"):
            out["filepath_local"] = self.filepath_local.path

        try:
            out["absolute_url"] = self.get_absolute_url()
        except NoReverseMatch:
            raise InvalidDocumentError(
                "Unable to save to index due to missing absolute_url: %s"
                % self.pk
            )

        # Docket Entry
        out["description"] = self.docket_entry.description
        if self.docket_entry.entry_number is not None:
            out["entry_number"] = self.docket_entry.entry_number
        if self.docket_entry.date_filed is not None:
            out["entry_date_filed"] = midnight_pst(
                self.docket_entry.date_filed
            )

        text_template = loader.get_template("indexes/dockets_text.txt")
        out["text"] = text_template.render({"item": self}).translate(null_map)

        return normalize_search_dicts(out)


class BankruptcyInformation(models.Model):
    docket = models.OneToOneField(
        Docket,
        help_text="The docket that the bankruptcy info is associated with.",
        on_delete=models.CASCADE,
        related_name="bankruptcy_information",
    )
    date_created = models.DateTimeField(
        help_text="The date time this item was created.",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="Timestamp of last update.", auto_now=True, db_index=True,
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
        help_text="The last date for filing claims.", blank=True, null=True,
    )
    date_last_to_file_govt = models.DateTimeField(
        help_text="The last date for the government to file claims.",
        blank=True,
        null=True,
    )
    date_debtor_dismissed = models.DateTimeField(
        help_text="The date the debtor was dismissed.", blank=True, null=True,
    )
    chapter = models.CharField(
        help_text="The chapter the bankruptcy is currently filed under.",
        max_length=10,
        blank=True,
    )
    trustee_str = models.TextField(
        help_text="The name of the trustee handling the case.", blank=True,
    )

    class Meta:
        verbose_name_plural = "Bankruptcy Information"

    def __unicode__(self):
        return "Bankruptcy Info for docket %s" % self.docket_id


class Claim(models.Model):
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
    date_created = models.DateTimeField(
        help_text="The date time this item was created.",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="Timestamp of last update.", auto_now=True, db_index=True,
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
        help_text="Date the last amendment was filed.", blank=True, null=True,
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
        help_text="The status of the claim.", max_length=1000, blank=True,
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

    def __unicode__(self):
        return "Claim #%s on docket %s with pk %s" % (
            self.claim_number,
            self.docket_id,
            self.pk,
        )


class ClaimHistory(AbstractPacerDocument, AbstractPDF):
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
        help_text="The created date of the claim.", null=True, blank=True,
    )
    claim_document_type = models.IntegerField(
        help_text=(
            "The type of document that is used in the history row for "
            "the claim. One of: %s"
        )
        % ", ".join(["%s (%s)" % (t[0], t[1]) for t in CLAIM_TYPES]),
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
            "The cased ID provided by PACER. Noted in this case on a "
            "per-document-level, since we've learned that some "
            "documents from other cases can appear in curious places."
        ),
        max_length=100,
        blank=True,
    )

    class Meta:
        verbose_name_plural = "Claim History Entries"


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
        (STATE_ATTORNEY_GENERAL, "State Attorney General"),
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
    id = models.CharField(
        help_text="a unique ID for each court as used in URLs",
        max_length=15,  # Changes here will require updates in urls.py
        primary_key=True,
    )
    pacer_court_id = models.PositiveSmallIntegerField(
        help_text=(
            "The numeric ID for the court in PACER. "
            "This can be found by looking at the first three "
            "digits of any doc1 URL in PACER."
        ),
        null=True,
        blank=True,
    )
    pacer_has_rss_feed = models.NullBooleanField(
        help_text=(
            "Whether the court has a PACER RSS feed. If null, this "
            "doesn't apply to the given court."
        ),
        blank=True,
    )
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
        help_text="a short name of the court", max_length=100, blank=False,
    )
    full_name = models.CharField(
        help_text="the full name of the court", max_length=200, blank=False,
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
        % ", ".join(["%s (%s)" % (t[0], t[1]) for t in JURISDICTIONS]),
        max_length=3,
        choices=JURISDICTIONS,
    )
    notes = models.TextField(
        help_text="any notes about coverage or anything else (currently very "
        "raw)",
        blank=True,
    )

    def __unicode__(self):
        return u"{name}".format(name=self.full_name)

    @property
    def is_terminated(self):
        if self.end_date:
            return True
        return False

    class Meta:
        ordering = ["position"]


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
                from cl.citations.find_citations import get_citations

                c = get_citations(
                    citation_str,
                    html=False,
                    do_post_citation=False,
                    do_defendant=False,
                    disambiguate=False,
                )[0]
            except IndexError:
                raise ValueError(
                    "Unable to parse citation '%s'" % citation_str
                )
            else:
                clone.query.add_q(
                    Q(
                        citations__volume=c.volume,
                        citations__reporter=c.reporter,
                        citations__page=c.page,
                    )
                )

        # Add the rest of the args & kwargs
        clone.query.add_q(Q(*args, **kwargs))
        return clone


class OpinionCluster(models.Model):
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
    date_created = models.DateTimeField(
        help_text="The time when this item was created",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text=(
            "The last moment when the item was modified. A value in "
            "year 1750 indicates the value is unknown"
        ),
        auto_now=True,
        db_index=True,
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
        % ", ".join(["%s (%s)" % (t[0], t[1]) for t in SOURCES]),
        max_length=10,
        choices=SOURCES,
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
        help_text="The procedural posture of the case.", blank=True,
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
        "%s" % ", ".join([t[0] for t in DOCUMENT_STATUSES]),
        max_length=50,
        blank=True,
        choices=DOCUMENT_STATUSES,
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

    objects = ClusterCitationQuerySet.as_manager()

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
            caption += ", %s" % self.docket.docket_number
        else:
            if citations[0].type == Citation.NEUTRAL:
                caption += ", %s" % citations[0]
                # neutral cites lack the parentheses, so we're done here.
                return caption
            elif (
                citations[0].type == Citation.WEST
                and citations[1].type == Citation.LEXIS
            ):
                caption += ", %s, %s" % (citations[0], citations[1])
            else:
                caption += ", %s" % citations[0]

        if self.docket.court_id != "scotus":
            court = re.sub(u" ", u"&nbsp;", self.docket.court.citation_string)
            # Strftime fails before 1900. Do it this way instead.
            year = self.date_filed.isoformat().split("-")[0]
            caption += "&nbsp;({court}&nbsp;{year})".format(
                court=court, year=year
            )
        return caption

    @property
    def citation_string(self):
        """Make a citation string, joined by commas"""
        citations = sorted(self.citations.all(), key=sort_cites)
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

    @property
    def authority_count(self):
        return self.authorities.count()

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

    @property
    def authorities_with_data(self):
        """Returns a list of this cluster's authorities with an extra field
        appended related to citation counts, for eventual injection into a
        view template.
        The returned list is sorted by that citation count field.
        """
        authorities_with_data = list(self.authorities)
        for authority in authorities_with_data:
            authority.citation_depth = get_citation_depth_between_clusters(
                citing_cluster_pk=self.pk, cited_cluster_pk=authority.pk,
            )

        authorities_with_data.sort(
            key=lambda x: x.citation_depth, reverse=True
        )
        return authorities_with_data

    def top_visualizations(self):
        return self.visualizations.filter(
            published=True, deleted=False
        ).order_by("-view_count")

    def __unicode__(self):
        if self.case_name:
            return u"%s: %s" % (self.pk, self.case_name)
        else:
            return u"%s" % self.pk

    def get_absolute_url(self):
        return reverse("view_case", args=[self.pk, self.slug])

    def save(self, index=True, force_commit=False, *args, **kwargs):
        self.slug = slugify(trunc(best_case_name(self), 75))
        super(OpinionCluster, self).save(*args, **kwargs)
        if index:
            from cl.search.tasks import add_items_to_solr

            add_items_to_solr.delay(
                [self.pk], "search.OpinionCluster", force_commit
            )

    def delete(self, *args, **kwargs):
        """
        Note that this doesn't get called when an entire queryset
        is deleted, but that should be OK.
        """
        id_cache = self.pk
        super(OpinionCluster, self).delete(*args, **kwargs)
        from cl.search.tasks import delete_items

        delete_items.delay([id_cache], "search.Opinion")

    def as_search_list(self):
        # IDs
        out = {}

        # Court
        court = {
            "court_id": self.docket.court.pk,
            "court": self.docket.court.full_name,
            "court_citation_string": self.docket.court.citation_string,
            "court_exact": self.docket.court_id,
        }
        out.update(court)

        # Docket
        docket = {
            "docket_id": self.docket_id,
            "docketNumber": self.docket.docket_number,
        }
        if self.docket.date_argued is not None:
            docket["dateArgued"] = midnight_pst(self.docket.date_argued)
        if self.docket.date_reargued is not None:
            docket["dateReargued"] = midnight_pst(self.docket.date_reargued)
        if self.docket.date_reargument_denied is not None:
            docket["dateReargumentDenied"] = midnight_pst(
                self.docket.date_reargument_denied
            )
        out.update(docket)

        # Cluster
        out.update(
            {
                "cluster_id": self.pk,
                "caseName": best_case_name(self),
                "caseNameShort": self.case_name_short,
                "panel_ids": [judge.pk for judge in self.panel.all()],
                "non_participating_judge_ids": [
                    judge.pk for judge in self.non_participating_judges.all()
                ],
                "judge": self.judges,
                "citation": [str(cite) for cite in self.citations.all()],
                "scdb_id": self.scdb_id,
                "source": self.source,
                "attorney": self.attorneys,
                "suitNature": self.nature_of_suit,
                "citeCount": self.citation_count,
                "status": self.get_precedential_status_display(),
                "status_exact": self.get_precedential_status_display(),
                "sibling_ids": [
                    sibling.pk for sibling in self.sub_opinions.all()
                ],
            }
        )
        try:
            out["lexisCite"] = str(
                self.citations.filter(type=Citation.LEXIS)[0]
            )
        except IndexError:
            pass
        try:
            out["neutralCite"] = str(
                self.citations.filter(type=Citation.NEUTRAL)[0]
            )
        except IndexError:
            pass

        if self.date_filed is not None:
            out["dateFiled"] = midnight_pst(self.date_filed)
        try:
            out["absolute_url"] = self.get_absolute_url()
        except NoReverseMatch:
            raise InvalidDocumentError(
                "Unable to save to index due to missing absolute_url "
                "(court_id: %s, item.pk: %s). Might the court have in_use set "
                "to False?" % (self.docket.court_id, self.pk)
            )

        # Opinion
        search_list = []
        text_template = loader.get_template("indexes/opinion_text.txt")
        for opinion in self.sub_opinions.all():
            # Always make a copy to get a fresh version above metadata. Failure
            # to do this pushes metadata from previous iterations to objects
            # where it doesn't belong.
            out_copy = out.copy()
            out_copy.update(
                {
                    "id": opinion.pk,
                    "cites": [o.pk for o in opinion.opinions_cited.all()],
                    "author_id": getattr(opinion.author, "pk", None),
                    "joined_by_ids": [j.pk for j in opinion.joined_by.all()],
                    "type": opinion.type,
                    "download_url": opinion.download_url or None,
                    "local_path": unicode(opinion.local_path),
                    "text": text_template.render(
                        {
                            "item": opinion,
                            "citation_string": self.citation_string,
                        }
                    ).translate(null_map),
                }
            )

            search_list.append(normalize_search_dicts(out_copy))

        return search_list


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
    )
    cluster = models.ForeignKey(
        OpinionCluster,
        help_text="The cluster that the citation applies to",
        related_name="citations",
        on_delete=models.CASCADE,
    )
    volume = models.SmallIntegerField(help_text="The volume of the reporter",)
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
        help_text="The type of citation that this is.", choices=CITATION_TYPES,
    )

    def __unicode__(self):
        # Note this representation is used in the front end.
        return u"{volume} {reporter} {page}".format(**self.__dict__)

    def get_absolute_url(self):
        return self.cluster.get_absolute_url()

    class Meta:
        index_together = (
            # To look up individual citations
            ("volume", "reporter", "page"),
            # To generate reporter volume lists
            ("volume", "reporter"),
        )
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


class Opinion(models.Model):
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
        on_delete=models.CASCADE,
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
    date_created = models.DateTimeField(
        help_text="The original creation date for the item",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text=(
            "The last moment when the item was modified. A value in "
            "year 1750 indicates the value is unknown"
        ),
        auto_now=True,
        db_index=True,
    )
    type = models.CharField(max_length=20, choices=OPINION_TYPES,)
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
            "The location, relative to MEDIA_ROOT on the CourtListener "
            "server, where files are stored"
        ),
        upload_to=make_upload_path,
        storage=IncrementingFileSystemStorage(),
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
        help_text="HTML of Columbia archive", blank=True,
    )
    xml_harvard = models.TextField(
        help_text="XML of Harvard CaseLaw Access Project opinion", blank=True,
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

    @property
    def siblings(self):
        # These are other sub-opinions of the current cluster.
        return self.cluster.sub_opinions

    def __unicode__(self):
        try:
            return u"{pk} - {cn}".format(
                pk=getattr(self, "pk", None), cn=self.cluster.case_name,
            )
        except AttributeError:
            return u"Orphan opinion with ID: %s" % self.pk

    def get_absolute_url(self):
        return reverse("view_case", args=[self.cluster.pk, self.cluster.slug])

    def clean(self):
        if self.type == "":
            raise ValidationError("'type' is a required field.")

    def save(self, index=True, force_commit=False, *args, **kwargs):
        super(Opinion, self).save(*args, **kwargs)
        if index:
            from cl.search.tasks import add_items_to_solr

            add_items_to_solr.delay([self.pk], "search.Opinion", force_commit)

    def as_search_dict(self):
        """Create a dict that can be ingested by Solr."""
        # IDs
        out = {
            "id": self.pk,
            "docket_id": self.cluster.docket.pk,
            "cluster_id": self.cluster.pk,
            "court_id": self.cluster.docket.court.pk,
        }

        # Opinion
        out.update(
            {
                "cites": [opinion.pk for opinion in self.opinions_cited.all()],
                "author_id": getattr(self.author, "pk", None),
                # 'per_curiam': self.per_curiam,
                "joined_by_ids": [judge.pk for judge in self.joined_by.all()],
                "type": self.type,
                "download_url": self.download_url or None,
                "local_path": unicode(self.local_path),
            }
        )

        # Cluster
        out.update(
            {
                "caseName": best_case_name(self.cluster),
                "caseNameShort": self.cluster.case_name_short,
                "sibling_ids": [sibling.pk for sibling in self.siblings.all()],
                "panel_ids": [judge.pk for judge in self.cluster.panel.all()],
                "non_participating_judge_ids": [
                    judge.pk
                    for judge in self.cluster.non_participating_judges.all()
                ],
                "judge": self.cluster.judges,
                "citation": [
                    str(cite) for cite in self.cluster.citations.all()
                ],
                "scdb_id": self.cluster.scdb_id,
                "source": self.cluster.source,
                "attorney": self.cluster.attorneys,
                "suitNature": self.cluster.nature_of_suit,
                "citeCount": self.cluster.citation_count,
                "status": self.cluster.get_precedential_status_display(),
                "status_exact": self.cluster.get_precedential_status_display(),
            }
        )
        try:
            out["lexisCite"] = str(
                self.cluster.citations.filter(type=Citation.LEXIS)[0]
            )
        except IndexError:
            pass

        try:
            out["neutralCite"] = str(
                self.cluster.citations.filter(type=Citation.NEUTRAL)[0]
            )
        except IndexError:
            pass

        if self.cluster.date_filed is not None:
            out["dateFiled"] = midnight_pst(self.cluster.date_filed)
        try:
            out["absolute_url"] = self.cluster.get_absolute_url()
        except NoReverseMatch:
            raise InvalidDocumentError(
                "Unable to save to index due to missing absolute_url "
                "(court_id: %s, item.pk: %s). Might the court have in_use set "
                "to False?" % (self.cluster.docket.court_id, self.pk)
            )

        # Docket
        docket = {"docketNumber": self.cluster.docket.docket_number}
        if self.cluster.docket.date_argued is not None:
            docket["dateArgued"] = midnight_pst(
                self.cluster.docket.date_argued
            )
        if self.cluster.docket.date_reargued is not None:
            docket["dateReargued"] = midnight_pst(
                self.cluster.docket.date_reargued
            )
        if self.cluster.docket.date_reargument_denied is not None:
            docket["dateReargumentDenied"] = midnight_pst(
                self.cluster.docket.date_reargument_denied
            )
        out.update(docket)

        court = {
            "court": self.cluster.docket.court.full_name,
            "court_citation_string": self.cluster.docket.court.citation_string,
            "court_exact": self.cluster.docket.court_id,  # For faceting
        }
        out.update(court)

        # Load the document text using a template for cleanup and concatenation
        text_template = loader.get_template("indexes/opinion_text.txt")
        out["text"] = text_template.render(
            {"item": self, "citation_string": self.cluster.citation_string}
        ).translate(null_map)

        return normalize_search_dicts(out)


class OpinionsCited(models.Model):
    citing_opinion = models.ForeignKey(
        Opinion, related_name="cited_opinions", on_delete=models.CASCADE,
    )
    cited_opinion = models.ForeignKey(
        Opinion, related_name="citing_opinions", on_delete=models.CASCADE,
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

    def __unicode__(self):
        return u"%s ⤜--cites⟶  %s" % (
            self.citing_opinion.id,
            self.cited_opinion.id,
        )

    class Meta:
        verbose_name_plural = "Opinions cited"
        unique_together = ("citing_opinion", "cited_opinion")


class Tag(models.Model):
    date_created = models.DateTimeField(
        help_text="The original creation date for the item",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text=(
            "The last moment when the item was modified. A value in "
            "year 1750 indicates the value is unknown"
        ),
        auto_now=True,
        db_index=True,
    )
    name = models.CharField(
        help_text="The name of the tag.",
        max_length=50,
        db_index=True,
        unique=True,
    )

    def __unicode__(self):
        return u"%s: %s" % (self.pk, self.name)

    def tag_object(self, thing):
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
#         on_delete=models.CASCADE,
#     )
#     lower_court = models.ForeignKey(
#         Court,
#         related_name='reviewed_by',
#         on_delete=models.CASCADE,
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
#     def __unicode__(self):
#         return u'%s ⤜--reviewed by⟶  %s' % (self.lower_court.id,
#                                         self.upper_court.id)
#
#     class Meta:
#         unique_together = ("upper_court", "lower_court")
class SEARCH_TYPES:
    OPINION = "o"
    RECAP = "r"
    ORAL_ARGUMENT = "oa"
    PEOPLE = "p"
    NAMES = (
        (OPINION, "Opinions"),
        (RECAP, "RECAP"),
        (ORAL_ARGUMENT, "Oral Arguments"),
        (PEOPLE, "People"),
    )
    ALL_TYPES = [OPINION, RECAP, ORAL_ARGUMENT, PEOPLE]
