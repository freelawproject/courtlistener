# coding=utf-8
import os
import re
from datetime import datetime, time

from celery.canvas import chain
from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.core.exceptions import ValidationError
from django.core.urlresolvers import reverse, NoReverseMatch
from django.db import models
from django.db.models import Prefetch
from django.template import loader
from django.utils.encoding import smart_unicode
from django.utils.text import slugify

from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.lib import fields
from cl.lib.model_helpers import make_upload_path, make_recap_path, \
    make_recap_pdf_path
from cl.lib.search_index_utils import InvalidDocumentError, null_map, \
    normalize_search_dicts
from cl.lib.storage import IncrementingFileSystemStorage
from cl.lib.string_utils import trunc

DOCUMENT_STATUSES = (
    ('Published', 'Precedential'),
    ('Unpublished', 'Non-Precedential'),
    ('Errata', 'Errata'),
    ('Separate', 'Separate Opinion'),
    ('In-chambers', 'In-chambers'),
    ('Relating-to', 'Relating-to orders'),
    ('Unknown', 'Unknown Status'),
)

SOURCES = (
    ('C', 'court website'),
    ('R', 'public.resource.org'),
    ('CR', 'court website merged with resource.org'),
    ('L', 'lawbox'),
    ('LC', 'lawbox merged with court'),
    ('LR', 'lawbox merged with resource.org'),
    ('LCR', 'lawbox merged with court and resource.org'),
    ('M', 'manual input'),
    ('A', 'internet archive'),
    ('H', 'brad heath archive'),
    ('Z', 'columbia archive'),
    ('ZC', 'columbia merged with court'),
    ('ZLC', 'columbia merged with lawbox and court'),
    ('ZLR', 'columbia merged with lawbox and resource.org'),
    ('ZLCR', 'columbia merged with lawbox, court, and resource.org'),
    ('ZR', 'columbia merged with resource.org'),
    ('ZCR', 'columbia merged with court and resource.org'),
    ('ZL', 'columbia merged with lawbox'),
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
        help_text="The docket number in the lower court.",
        blank=True,
    )
    assigned_to = models.ForeignKey(
        'people_db.Person',
        related_name='original_court_info',
        help_text="The judge the case was assigned to.",
        null=True,
        blank=True,
    )
    assigned_to_str = models.TextField(
        help_text="The judge that the case was assigned to, as a string.",
        blank=True,
    )
    court_reporter = models.TextField(
        help_text="The court reporter responsible for the case.",
        blank=True,
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
    date_judgement = models.DateField(
        help_text="The date of the order or judgement in the lower court.",
        blank=True,
        null=True,
    )
    date_judgement_oed = models.DateField(
        help_text="The date the judgement was entered on the docket at the "
                  "lower court.",
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

    class Meta:
        verbose_name_plural = 'Originating Court Information'


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
    SOURCE_CHOICES = (
        (DEFAULT, "Default"),
        (RECAP, "RECAP"),
        (SCRAPER, "Scraper"),
        (RECAP_AND_SCRAPER, "RECAP and Scraper"),
        (COLUMBIA, "Columbia"),
        (COLUMBIA_AND_SCRAPER, "Columbia and Scraper"),
        (COLUMBIA_AND_RECAP, 'Columbia and RECAP'),
        (COLUMBIA_AND_RECAP_AND_SCRAPER, "Columbia, RECAP and Scraper"),
    )
    RECAP_SOURCES = [RECAP, RECAP_AND_SCRAPER, COLUMBIA_AND_RECAP,
                     COLUMBIA_AND_RECAP_AND_SCRAPER]

    source = models.SmallIntegerField(
        help_text="contains the source of the Docket.",
        choices=SOURCE_CHOICES,
    )
    court = models.ForeignKey(
        'Court',
        help_text="The court where the docket was filed",
        db_index=True,
        related_name='dockets',
    )
    appeal_from = models.ForeignKey(
        'Court',
        help_text="In appellate cases, this is the lower court or "
                  "administrative body where this case was originally heard. "
                  "This field is frequently blank due to it not being "
                  "populated historically or due to our inability to "
                  "normalize the value in appeal_from_str.",
        related_name='+',
        blank=True,
        null=True,
    )
    appeal_from_str = models.TextField(
        help_text="In appeallate cases, this is the lower court or "
                  "administrative body where this case was originally heard. "
                  "This field is frequently blank due to it not being "
                  "populated historically. This field may have values when "
                  "the appeal_from field does not. That can happen if we are "
                  "unable to normalize the value in this field.",
        blank=True,
    )
    originating_court_information = models.OneToOneField(
        OriginatingCourtInformation,
        help_text="Lower court information for appellate dockets",
        related_name="docket",
        blank=True,
        null=True,
    )
    tags = models.ManyToManyField(
        'search.Tag',
        help_text="The tags associated with the docket.",
        related_name="dockets",
        blank=True,
    )
    html_documents = GenericRelation(
        'recap.PacerHtmlFiles',
        help_text="Original HTML files collected from PACER.",
        related_query_name='dockets',
        null=True,
        blank=True,
    )
    assigned_to = models.ForeignKey(
        'people_db.Person',
        related_name='assigning',
        help_text="The judge the case was assigned to.",
        null=True,
        blank=True,
    )
    assigned_to_str = models.TextField(
        help_text="The judge that the case was assigned to, as a string.",
        blank=True,
    )
    referred_to = models.ForeignKey(
        'people_db.Person',
        related_name='referring',
        help_text="The judge to whom the 'assigned_to' judge is delegated.",
        null=True,
        blank=True,
    )
    referred_to_str = models.TextField(
        help_text="The judge that the case was referred to, as a string.",
        blank=True,
    )
    panel = models.ManyToManyField(
        'people_db.Person',
        help_text="The empaneled judges for the case. Currently an unused "
                  "field but planned to be used in conjunction with the "
                  "panel_str field.",
        related_name="empanelled_dockets",
        blank=True,
    )
    panel_str = models.TextField(
        help_text="The initials of the judges on the panel that heard this "
                  "case. This field is similar to the 'judges' field on "
                  "the cluster, but contains initials instead of full judge "
                  "names, and applies to the case on the whole instead of "
                  "only to a specific decision.",
        blank=True,
    )
    parties = models.ManyToManyField(
        'people_db.Party',
        help_text="The parties involved in the docket",
        related_name="dockets",
        through='people_db.PartyType',
        blank=True,
    )
    date_created = models.DateTimeField(
        help_text="The time when this item was created",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified. A value in "
                  "year 1750 indicates the value is unknown",
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
        help_text="The date the case was filed.",
        blank=True,
        null=True,
    )
    date_terminated = models.DateField(
        help_text="The date the case was terminated.",
        blank=True,
        null=True,
    )
    date_last_filing = models.DateField(
        help_text="The date the case was last updated in the docket, as shown "
                  "in PACER's Docket History report.",
        blank=True,
        null=True,
    )
    case_name_short = models.TextField(
        help_text="The abridged name of the case, often a single word, e.g. "
                  "'Marsh'",
        blank=True,
    )
    case_name = models.TextField(
        help_text="The standard name of the case",
        blank=True,
    )
    case_name_full = models.TextField(
        help_text="The full name of the case",
        blank=True,
    )
    slug = models.SlugField(
        help_text="URL that the document should map to (the slug)",
        max_length=75,
        db_index=False,
        blank=True,
    )
    docket_number = fields.CharNullField(
        help_text="The docket numbers of a case, can be consolidated and "
                  "quite long",
        max_length=5000,  # was 50, 100, 300, 1000
        blank=True,
        null=True,
        db_index=True,
    )
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
        help_text="The compensation demand.",
        max_length=500,
        blank=True,
    )
    jurisdiction_type = models.CharField(
        help_text="Stands for jurisdiction in RECAP XML docket. For example, "
                  "'Diversity', 'U.S. Government Defendant'.",
        max_length=100,
        blank=True,
    )
    appellate_fee_status = models.TextField(
        help_text="The status of the fee in the appellate court. Can be used "
                  "as a hint as to whether the government is the appellant "
                  "(in which case the fee is waived).",
        blank=True,
    )
    appellate_case_type_information = models.TextField(
        help_text="Information about a case from the appellate docket in "
                  "PACER. For example, 'civil, private, bankruptcy'.",
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
    view_count = models.IntegerField(
        help_text="The number of times the docket has been seen.",
        default=0,
    )
    date_blocked = models.DateField(
        help_text="The date that this opinion was blocked from indexing by "
                  "search engines",
        blank=True,
        null=True,
        db_index=True,
    )
    blocked = models.BooleanField(
        help_text="Whether a document should be blocked from indexing by "
                  "search engines",
        db_index=True,
        default=False,
    )

    class Meta:
        unique_together = ('docket_number', 'pacer_case_id', 'court')

    def __unicode__(self):
        if self.case_name:
            return smart_unicode('%s: %s' % (self.pk, self.case_name))
        else:
            return u'{pk}'.format(pk=self.pk)

    def save(self, *args, **kwargs):
        self.slug = slugify(trunc(best_case_name(self), 75))
        if self.source in self.RECAP_SOURCES:
            for field in ['pacer_case_id', 'docket_number']:
                if not getattr(self, field, None):
                    raise ValidationError("'%s' cannot be Null or empty in "
                                          "RECAP documents." % field)

        super(Docket, self).save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('view_docket', args=[self.pk, self.slug])

    @property
    def pacer_url(self):
        if not self.pacer_case_id:
            return None
        from cl.lib.pacer import map_cl_to_pacer_id
        court_id = map_cl_to_pacer_id(self.court.pk)
        if self.court.jurisdiction == Court.FEDERAL_APPELLATE:
            return (u'https://ecf.%s.uscourts.gov'
                    '/n/beam/servlet/TransportRoom?'
                    u'servlet=CaseSummary.jsp&'
                    u'caseNum=%s&'
                    u'incOrigDkt=Y&'
                    u'incDktEntries=Y') % (
                court_id,
                self.pacer_case_id,
            )
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
            Prefetch('attorneys',
                     queryset=Attorney.objects.filter(
                         roles__docket=self
                     ).distinct().only('pk', 'name'),
                     to_attr='attys_in_docket'),
            Prefetch('attys_in_docket__organizations',
                     queryset=AttorneyOrganization.objects.filter(
                         attorney_organization_associations__docket=self
                     ).distinct().only('pk', 'name'),
                     to_attr='firms_in_docket')
        )

    def as_search_list(self):
        """Create list of search dicts from a single docket. This should be
        faster than creating a search dict per document on the docket.
        """
        search_list = []

        # Docket
        out = {
            'docketNumber': self.docket_number,
            'caseName': best_case_name(self),
            'suitNature': self.nature_of_suit,
            'cause': self.cause,
            'juryDemand': self.jury_demand,
            'jurisdictionType': self.jurisdiction_type,
        }
        if self.date_argued is not None:
            out['dateArgued'] = datetime.combine(self.date_argued, time())
        if self.date_filed is not None:
            out['dateFiled'] = datetime.combine(self.date_filed, time())
        if self.date_terminated is not None:
            out['dateTerminated'] = datetime.combine(
                self.date_terminated, time())
        try:
            out['docket_absolute_url'] = self.get_absolute_url()
        except NoReverseMatch:
            raise InvalidDocumentError("Unable to save to index due to "
                                       "missing absolute_url: %s" % self.pk)

        # Judges
        if self.assigned_to is not None:
            out['assignedTo'] = self.assigned_to.name_full
        elif self.assigned_to_str:
            out['assignedTo'] = self.assigned_to_str
        if self.referred_to is not None:
            out['referredTo'] = self.referred_to.name_full
        elif self.referred_to_str:
            out['referredTo'] = self.referred_to_str

        # Court
        out.update({
            'court': self.court.full_name,
            'court_exact': self.court_id,  # For faceting
            'court_citation_string': self.court.citation_string,
        })

        # Parties, attorneys, firms
        out.update({
            'party_id': set(),
            'party': set(),
            'attorney_id': set(),
            'attorney': set(),
            'firm_id': set(),
            'firm': set(),
        })
        for p in self.prefetched_parties:
            out['party_id'].add(p.pk)
            out['party'].add(p.name)
            for a in p.attys_in_docket:
                out['attorney_id'].add(a.pk)
                out['attorney'].add(a.name)
                for f in a.firms_in_docket:
                    out['firm_id'].add(f.pk)
                    out['firm'].add(f.name)

        # Do RECAPDocument and Docket Entries in a nested loop
        for de in self.docket_entries.all():
            # Docket Entry
            out['description'] = de.description
            if de.entry_number is not None:
                out['entry_number'] = de.entry_number
            if de.date_filed is not None:
                out['entry_date_filed'] = datetime.combine(de.date_filed,
                                                           time())
            rds = de.recap_documents.all()

            if len(rds) == 0:
                # Minute entry or other entry that lacks docs.
                # For now, we punt.
                # https://github.com/freelawproject/courtlistener/issues/784
                continue

            for rd in rds:
                # IDs
                out.update({
                    'id': rd.pk,
                    'docket_entry_id': de.pk,
                    'docket_id': self.pk,
                    'court_id': self.court.pk,
                    'assigned_to_id': getattr(self.assigned_to, 'pk', None),
                    'referred_to_id': getattr(self.referred_to, 'pk', None),
                })

                # RECAPDocument
                out.update({
                    'short_description': rd.description,
                    'document_type': rd.get_document_type_display(),
                    'document_number': rd.document_number,
                    'attachment_number': rd.attachment_number,
                    'is_available': rd.is_available,
                    'page_count': rd.page_count,
                })
                if hasattr(rd.filepath_local, 'path'):
                    out['filepath_local'] = rd.filepath_local.path
                try:
                    out['absolute_url'] = rd.get_absolute_url()
                except NoReverseMatch:
                    raise InvalidDocumentError(
                        "Unable to save to index due to missing absolute_url: "
                        "%s" % self.pk
                    )

                text_template = loader.get_template('indexes/dockets_text.txt')
                out['text'] = text_template.render({'item': rd}).translate(
                    null_map)

                search_list.append(normalize_search_dicts(out))

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
            process_docket_data(self, self.filepath_local.path,
                                UPLOAD_TYPE.IA_XML_FILE)

        # Then layer the uploads on top of that.
        for html in self.html_documents.order_by('date_created'):
            process_docket_data(self, html.filepath.path, html.upload_type)


class DocketEntry(models.Model):

    docket = models.ForeignKey(
        Docket,
        help_text="Foreign key as a relation to the corresponding Docket "
                  "object. Specifies which docket the docket entry "
                  "belongs to.",
        related_name="docket_entries",
    )
    tags = models.ManyToManyField(
        'search.Tag',
        help_text="The tags associated with the docket entry.",
        related_name="docket_entries",
        blank=True,
    )
    html_documents = GenericRelation(
        'recap.PacerHtmlFiles',
        help_text="HTML attachment files collected from PACER.",
        related_query_name='docket_entries',
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
        help_text="# on the PACER docket page.",
    )
    description = models.TextField(
        help_text="The text content of the docket entry that appears in the "
                  "PACER docket page.",
        blank=True,
    )

    class Meta:
        unique_together = ('docket', 'entry_number')
        verbose_name_plural = 'Docket Entries'
        ordering = ('entry_number',)
        permissions = (
            ("has_recap_api_access", "Can work with RECAP API"),
        )

    def __unicode__(self):
        return "<DocketEntry:%s ---> %s >" % (
            self.pk,
            trunc(self.description, 50, ellipsis="...")
        )


class RECAPDocument(models.Model):
    """
        The model for Docket Documents and Attachments.
    """
    PACER_DOCUMENT = 1
    ATTACHMENT = 2
    DOCUMENT_TYPES = (
        (PACER_DOCUMENT, "PACER Document"),
        (ATTACHMENT, "Attachment"),
    )
    OCR_COMPLETE = 1
    OCR_UNNECESSARY = 2
    OCR_FAILED = 3
    OCR_NEEDED = 4
    OCR_STATUSES = (
        (OCR_COMPLETE, "OCR Complete"),
        (OCR_UNNECESSARY, "OCR Not Necessary"),
        (OCR_FAILED, "OCR Failed"),
        (OCR_NEEDED, "OCR Needed"),
    )
    docket_entry = models.ForeignKey(
        DocketEntry,
        help_text="Foreign Key to the DocketEntry object to which it belongs. "
                  "Multiple documents can belong to a DocketEntry. "
                  "(Attachments and Documents together)",
        related_name="recap_documents",
    )
    tags = models.ManyToManyField(
        'search.Tag',
        help_text="The tags associated with the document.",
        related_name="recap_documents",
        blank=True,
    )
    date_created = models.DateTimeField(
        help_text="The date the file was imported to Local Storage.",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="Timestamp of last update.",
        auto_now=True,
        db_index=True,
    )
    date_upload = models.DateTimeField(
        help_text="upload_date in RECAP. The date the file was uploaded to "
                  "RECAP. This information is provided by RECAP.",
        blank=True,
        null=True,
    )
    document_type = models.IntegerField(
        help_text="Whether this is a regular document or an attachment.",
        db_index=True,
        choices=DOCUMENT_TYPES,
    )
    document_number = models.CharField(
        help_text="If the file is a document, the number is the "
                  "document_number in RECAP docket.",
        max_length=32,
        db_index=True,
    )
    attachment_number = models.SmallIntegerField(
        help_text="If the file is an attachment, the number is the attachment "
                  "number in RECAP docket.",
        blank=True,
        null=True,
    )
    pacer_doc_id = models.CharField(
        help_text="The ID of the document in PACER. This information is "
                  "provided by RECAP.",
        max_length=32,  # Same as in RECAP
        blank=True,
    )
    is_available = models.NullBooleanField(
        help_text="True if the item is available in RECAP",
        blank=True,
        null=True,
        default=False,
    )
    sha1 = models.CharField(
        help_text="The ID used for a document in RECAP",
        max_length=40,  # As in RECAP
        blank=True,
    )
    page_count = models.IntegerField(
        help_text="The number of pages in the document, if known",
        blank=True,
        null=True,
    )
    filepath_local = models.FileField(
        help_text="The path of the file in the local storage area.",
        upload_to=make_recap_pdf_path,
        storage=IncrementingFileSystemStorage(),
        max_length=1000,
        blank=True,
    )
    filepath_ia = models.CharField(
        help_text="The URL of the file in IA",
        max_length=1000,
        blank=True,
    )
    ia_upload_failure_count = models.SmallIntegerField(
        help_text="Number of times the upload to the Internet Archive failed.",
        null=True,
        blank=True,
    )
    description = models.TextField(
        help_text="The short description of the docket entry that appears on "
                  "the attachments page.",
        blank=True,
    )
    plain_text = models.TextField(
        help_text="Plain text of the document after extraction using "
                  "pdftotext, wpd2txt, etc.",
        blank=True,
    )
    ocr_status = models.SmallIntegerField(
        help_text="The status of OCR processing on this item.",
        choices=OCR_STATUSES,
        null=True,
        blank=True,
    )
    is_free_on_pacer = models.NullBooleanField(
        help_text="Is this item freely available as an opinion on PACER?",
        db_index=True,
    )

    class Meta:
        unique_together = ('docket_entry', 'document_number',
                           'attachment_number')
        ordering = ("document_type", 'document_number', 'attachment_number')
        permissions = (
            ("has_recap_api_access", "Can work with RECAP API"),
        )

    def __unicode__(self):
        return "%s: Docket_%s , document_number_%s , attachment_number_%s" % (
            self.pk, self.docket_entry.docket.docket_number,
            self.document_number, self.attachment_number
        )

    def get_absolute_url(self):
        if self.document_type == self.PACER_DOCUMENT:
            return reverse('view_recap_document', kwargs={
                'docket_id': self.docket_entry.docket.pk,
                'doc_num': self.document_number,
                'slug': self.docket_entry.docket.slug,
            })
        elif self.document_type == self.ATTACHMENT:
            return reverse('view_recap_attachment', kwargs={
                'docket_id': self.docket_entry.docket.pk,
                'doc_num': self.document_number,
                'att_num': self.attachment_number,
                'slug': self.docket_entry.docket.slug,
            })

    @property
    def pacer_url(self):
        """Construct a doc1 URL for any item, if we can. Else, return None."""
        from cl.lib.pacer import map_cl_to_pacer_id
        court = self.docket_entry.docket.court
        court_id = map_cl_to_pacer_id(court.pk)
        if self.pacer_doc_id:
            if court.jurisdiction == Court.FEDERAL_APPELLATE:
                path = 'docs1'
            else:
                path = 'doc1'
            return "https://ecf.%s.uscourts.gov/%s/%s?caseid=%s" % (
                court_id,
                path,
                self.pacer_doc_id,
                self.docket_entry.docket.pacer_case_id,
            )
        else:
            if court.jurisdiction == Court.FEDERAL_APPELLATE:
                return ''
            else:
                attachment_number = self.attachment_number or ''
                return ('https://ecf.{court_id}.uscourts.gov/cgi-bin/'
                        'show_case_doc?'
                        '{document_number},'
                        '{pacer_case_id},'
                        '{attachment_number},'
                        '{magic_number},'.format(
                            court_id=court_id,
                            document_number=self.document_number,
                            pacer_case_id=self.docket_entry.docket.pacer_case_id,
                            attachment_number=attachment_number,
                            magic_number='',  # For future use.
                        ))

    @property
    def needs_extraction(self):
        """Does the item need extraction and does it have all the right
        fields? Items needing OCR still need extraction.
        """
        return all([
            self.ocr_status is None or self.ocr_status == self.OCR_NEEDED,
            self.is_available is True,
            # Has a value in filepath field, which points to a file.
            self.filepath_local and os.path.isfile(self.filepath_local.path),
        ])

    def save(self, do_extraction=False, index=False, *args, **kwargs):
        if self.document_type == self.ATTACHMENT:
            if self.attachment_number is None:
                raise ValidationError('attachment_number cannot be null'
                                      ' for an attachment.')

        if self.pacer_doc_id is None:
            # Juriscraper returns these as null values. Instead we want blanks.
            self.pacer_doc_id = ''

        if self.attachment_number is None:
            # Validate that we don't already have such an entry. This is needed
            # because None values in SQL are all considered different.
            exists = RECAPDocument.objects.exclude(pk=self.pk).filter(
                document_number=self.document_number,
                attachment_number=self.attachment_number,
                docket_entry=self.docket_entry,
            ).exists()
            if exists:
                raise ValidationError(
                    "Duplicate values violate save constraint. An object with "
                    "this document_number and docket_entry already exists: "
                    "(%s, %s)" % (self.document_number, self.docket_entry_id)
                )

        super(RECAPDocument, self).save(*args, **kwargs)
        tasks = []
        if do_extraction and self.needs_extraction:
            # Context extraction not done and is requested.
            from cl.scrapers.tasks import extract_recap_pdf
            tasks.append(extract_recap_pdf.si(self.pk))
        if index:
            from cl.search.tasks import add_or_update_recap_document
            tasks.append(add_or_update_recap_document.si([self.pk],
                                                         force_commit=False))
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
        delete_items.delay([id_cache], settings.SOLR_RECAP_URL)

    def get_docket_metadata(self):
        """The metadata for the item that comes from the Docket."""
        docket = self.docket_entry.docket
        # IDs
        out = {
            'docket_id': docket.pk,
            'court_id': docket.court.pk,
            'assigned_to_id': getattr(docket.assigned_to, 'pk', None),
            'referred_to_id': getattr(docket.referred_to, 'pk', None)
        }

        # Docket
        out.update({
            'docketNumber': docket.docket_number,
            'caseName': best_case_name(docket),
            'suitNature': docket.nature_of_suit,
            'cause': docket.cause,
            'juryDemand': docket.jury_demand,
            'jurisdictionType': docket.jurisdiction_type,
        })
        if docket.date_argued is not None:
            out['dateArgued'] = datetime.combine(docket.date_argued, time())
        if docket.date_filed is not None:
            out['dateFiled'] = datetime.combine(docket.date_filed, time())
        if docket.date_terminated is not None:
            out['dateTerminated'] = datetime.combine(docket.date_terminated,
                                                     time())
        try:
            out['docket_absolute_url'] = docket.get_absolute_url()
        except NoReverseMatch:
            raise InvalidDocumentError(
                "Unable to save to index due to missing absolute_url: %s"
                % self.pk
            )

        # Judges
        if docket.assigned_to is not None:
            out['assignedTo'] = docket.assigned_to.name_full
        elif docket.assigned_to_str:
            out['assignedTo'] = docket.assigned_to_str
        if docket.referred_to is not None:
            out['referredTo'] = docket.referred_to.name_full
        elif docket.referred_to_str:
            out['referredTo'] = docket.referred_to_str

        # Court
        out.update({
            'court': docket.court.full_name,
            'court_exact': docket.court_id,  # For faceting
            'court_citation_string': docket.court.citation_string
        })

        # Parties, Attorneys, Firms
        out.update({
            'party_id': set(),
            'party': set(),
            'attorney_id': set(),
            'attorney': set(),
            'firm_id': set(),
            'firm': set(),
        })
        for p in docket.prefetched_parties:
            out['party_id'].add(p.pk)
            out['party'].add(p.name)
            for a in p.attys_in_docket:
                out['attorney_id'].add(a.pk)
                out['attorney'].add(a.name)
                for f in a.firms_in_docket:
                    out['firm_id'].add(f.pk)
                    out['firm'].add(f.name)

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
        out.update({
            'id': self.pk,
            'docket_entry_id': self.docket_entry.pk,
        })

        # RECAPDocument
        out.update({
            'short_description': self.description,
            'document_type': self.get_document_type_display(),
            'document_number': self.document_number,
            'attachment_number': self.attachment_number,
            'is_available': self.is_available,
            'page_count': self.page_count,
        })
        if hasattr(self.filepath_local, 'path'):
            out['filepath_local'] = self.filepath_local.path

        try:
            out['absolute_url'] = self.get_absolute_url()
        except NoReverseMatch:
            raise InvalidDocumentError(
                "Unable to save to index due to missing absolute_url: %s"
                % self.pk
            )

        # Docket Entry
        out['description'] = self.docket_entry.description
        if self.docket_entry.entry_number is not None:
            out['entry_number'] = self.docket_entry.entry_number
        if self.docket_entry.date_filed is not None:
            out['entry_date_filed'] = datetime.combine(
                self.docket_entry.date_filed,
                time()
            )

        text_template = loader.get_template('indexes/dockets_text.txt')
        out['text'] = text_template.render({'item': self}).translate(null_map)

        return normalize_search_dicts(out)


class Court(models.Model):
    """A class to represent some information about each court, can be extended
    as needed."""
    # Note that spaces cannot be used in the keys, or else the SearchForm won't
    # work
    FEDERAL_APPELLATE = 'F'
    FEDERAL_DISTRICT = 'FD'
    FEDERAL_BANKRUPTCY = 'FB'
    FEDERAL_BANKRUPTCY_PANEL = 'FBP'
    FEDERAL_SPECIAL = 'FS'
    STATE_SUPREME = 'S'
    STATE_APPELLATE = 'SA'
    STATE_TRIAL = 'ST'
    STATE_SPECIAL = 'SS'
    STATE_ATTORNEY_GENERAL = 'SAG'
    COMMITTEE = 'C'
    INTERNATIONAL = 'I'
    TESTING_COURT = 'T'
    JURISDICTIONS = (
        (FEDERAL_APPELLATE, 'Federal Appellate'),
        (FEDERAL_DISTRICT, 'Federal District'),
        (FEDERAL_BANKRUPTCY, 'Federal Bankruptcy'),
        (FEDERAL_BANKRUPTCY_PANEL, 'Federal Bankruptcy Panel'),
        (FEDERAL_SPECIAL, 'Federal Special'),
        (STATE_SUPREME, 'State Supreme'),
        (STATE_APPELLATE, 'State Appellate'),
        (STATE_TRIAL, 'State Trial'),
        (STATE_SPECIAL, 'State Special'),
        (STATE_ATTORNEY_GENERAL, 'State Attorney General'),
        (COMMITTEE, 'Committee'),
        (INTERNATIONAL, 'International'),
        (TESTING_COURT, 'Testing'),
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
        help_text='a unique ID for each court as used in URLs',
        max_length=15,  # Changes here will require updates in urls.py
        primary_key=True
    )
    pacer_court_id = models.PositiveSmallIntegerField(
        help_text="The numeric ID for the court in PACER. "
                  "This can be found by looking at the first three "
                  "digits of any doc1 URL in PACER.",
        null=True,
        blank=True,
    )
    pacer_has_rss_feed = models.NullBooleanField(
        help_text="Whether the court has a PACER RSS feed. If null, this "
                  "doesn't apply to the given court.",
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
        help_text='Whether this jurisdiction is in use in CourtListener -- '
                  'increasingly True',
        default=False
    )
    has_opinion_scraper = models.BooleanField(
        help_text='Whether the jurisdiction has a scraper that obtains '
                  'opinions automatically.',
        default=False,
    )
    has_oral_argument_scraper = models.BooleanField(
        help_text='Whether the jurisdiction has a scraper that obtains oral '
                  'arguments automatically.',
        default=False,
    )
    position = models.FloatField(
        help_text='A dewey-decimal-style numeral indicating a hierarchical '
                  'ordering of jurisdictions',
        db_index=True,
        unique=True
    )
    citation_string = models.CharField(
        help_text='the citation abbreviation for the court '
                  'as dictated by Blue Book',
        max_length=100,
        blank=True
    )
    short_name = models.CharField(
        help_text='a short name of the court',
        max_length=100,
        blank=False,
    )
    full_name = models.CharField(
        help_text='the full name of the court',
        max_length='200',
        blank=False,
    )
    url = models.URLField(
        help_text='the homepage for each court or the closest thing thereto',
        max_length=500,
        blank=True,
    )
    start_date = models.DateField(
        help_text="the date the court was established, if known",
        blank=True,
        null=True
    )
    end_date = models.DateField(
        help_text="the date the court was abolished, if known",
        blank=True,
        null=True
    )
    jurisdiction = models.CharField(
        help_text='the jurisdiction of the court, one of: %s' %
                  ', '.join(['%s (%s)' % (t[0], t[1]) for t in JURISDICTIONS]),
        max_length=3,
        choices=JURISDICTIONS
    )
    notes = models.TextField(
        help_text="any notes about coverage or anything else (currently very "
                  "raw)",
        blank=True
    )

    def __unicode__(self):
        return u'{name}'.format(name=self.full_name)

    @property
    def is_terminated(self):
        if self.end_date:
            return True
        return False

    class Meta:
        ordering = ["position"]


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
    )
    panel = models.ManyToManyField(
        'people_db.Person',
        help_text="The judges that participated in the opinion",
        related_name="opinion_clusters_participating_judges",
        blank=True,
    )
    non_participating_judges = models.ManyToManyField(
        'people_db.Person',
        help_text="The judges that heard the case, but did not participate in "
                  "the opinion",
        related_name="opinion_clusters_non_participating_judges",
        blank=True,
    )
    judges = models.TextField(
        help_text="The judges that participated in the opinion as a simple "
                  "text string. This field is used when normalized judges "
                  "cannot be placed into the panel field.",
        blank=True,
    )
    date_created = models.DateTimeField(
        help_text="The time when this item was created",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified. A value in "
                  "year 1750 indicates the value is unknown",
        auto_now=True,
        db_index=True,
    )
    date_filed = models.DateField(
        help_text="The date the cluster of opinions was filed by the court",
        db_index=True
    )
    date_filed_is_approximate = models.BooleanField(
        help_text="For a variety of opinions getting the correct date filed is"
                  "very difficult. For these, we have used heuristics to "
                  "approximate the date.",
        default=False,
    )
    slug = models.SlugField(
        help_text="URL that the document should map to (the slug)",
        max_length=75,
        db_index=False,
        null=True,
    )
    citation_id = models.IntegerField(
        help_text="A legacy field that holds the primary key from the old "
                  "citation table. Used to serve legacy APIs.",
        db_index=True,
        null=True,
        blank=True,
    )
    case_name_short = models.TextField(
        help_text="The abridged name of the case, often a single word, e.g. "
                  "'Marsh'",
        blank=True,
    )
    case_name = models.TextField(
        help_text="The shortened name of the case",
        blank=True
    )
    case_name_full = models.TextField(
        help_text="The full name of the case",
        blank=True
    )
    federal_cite_one = models.CharField(
        help_text="Primary federal citation",
        db_index=True,
        max_length=50,
        blank=True,
    )
    federal_cite_two = models.CharField(
        help_text="Secondary federal citation",
        db_index=True,
        max_length=50,
        blank=True,
    )
    federal_cite_three = models.CharField(
        help_text="Tertiary federal citation",
        db_index=True,
        max_length=50,
        blank=True,
    )
    state_cite_one = models.CharField(
        help_text="Primary state citation",
        max_length=50,
        blank=True,
    )
    state_cite_two = models.CharField(
        help_text="Secondary state citation",
        max_length=50,
        blank=True,
    )
    state_cite_three = models.CharField(
        help_text="Tertiary state citation",
        max_length=50,
        blank=True,
    )
    state_cite_regional = models.CharField(
        help_text="Regional citation",
        max_length=50,
        blank=True,
    )
    specialty_cite_one = models.CharField(
        help_text="Specialty citation",
        max_length=50,
        blank=True,
    )
    scotus_early_cite = models.CharField(
        help_text="Early SCOTUS citation such as How., Black, Cranch., etc.",
        max_length=50,
        blank=True,
    )
    lexis_cite = models.CharField(
        help_text="LexisNexis citation (e.g. 1 LEXIS 38237)",
        max_length=50,
        blank=True,
    )
    westlaw_cite = models.CharField(
        help_text="WestLaw citation (e.g. 22 WL 238)",
        max_length=50,
        blank=True,
    )
    neutral_cite = models.CharField(
        help_text='Neutral citation',
        max_length=50,
        blank=True,
    )
    scdb_id = models.CharField(
        help_text='The ID of the item in the Supreme Court Database',
        max_length=10,
        db_index=True,
        blank=True,
    )
    scdb_decision_direction = models.IntegerField(
        help_text='the ideological "direction" of a decision in the Supreme '
                  'Court database. More details at: http://scdb.wustl.edu/'
                  'documentation.php?var=decisionDirection',
        choices=SCDB_DECISION_DIRECTIONS,
        blank=True,
        null=True,
    )
    scdb_votes_majority = models.IntegerField(
        help_text='the number of justices voting in the majority in a Supreme '
                  'Court decision. More details at: http://scdb.wustl.edu/'
                  'documentation.php?var=majVotes',
        blank=True,
        null=True,
    )
    scdb_votes_minority = models.IntegerField(
        help_text='the number of justices voting in the minority in a Supreme '
                  'Court decision. More details at: http://scdb.wustl.edu/'
                  'documentation.php?var=minVotes',
        blank=True,
        null=True,
    )
    source = models.CharField(
        help_text="the source of the cluster, one of: %s" %
                  ', '.join(['%s (%s)' % (t[0], t[1]) for t in SOURCES]),
        max_length=10,
        choices=SOURCES,
        blank=True
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
        help_text="The nature of the suit. For the moment can be codes or "
                  "laws or whatever",
        blank=True,
    )
    posture = models.TextField(
        help_text="The procedural posture of the case.",
        blank=True,
    )
    syllabus = models.TextField(
        help_text="A summary of the issues presented in the case and the "
                  "outcome.",
        blank=True,
    )
    citation_count = models.IntegerField(
        help_text='The number of times this document is cited by other '
                  'opinion',
        default=0,
        db_index=True,
    )
    precedential_status = models.CharField(
        help_text='The precedential status of document, one of: '
                  '%s' % ', '.join([t[0] for t in DOCUMENT_STATUSES]),
        max_length=50,
        blank=True,
        choices=DOCUMENT_STATUSES,
        db_index=True,
    )
    date_blocked = models.DateField(
        help_text="The date that this opinion was blocked from indexing by "
                  "search engines",
        blank=True,
        null=True,
        db_index=True,
    )
    blocked = models.BooleanField(
        help_text="Whether a document should be blocked from indexing by "
                  "search engines",
        db_index=True,
        default=False
    )

    @property
    def caption(self):
        """Make a proper caption"""
        caption = best_case_name(self)
        if self.neutral_cite:
            caption += ", %s" % self.neutral_cite
            # neutral cites lack the parentheses, so we're done here.
            return caption
        elif self.federal_cite_one:
            caption += ", %s" % self.federal_cite_one
        elif self.federal_cite_two:
            caption += ", %s" % self.federal_cite_two
        elif self.federal_cite_three:
            caption += ", %s" % self.federal_cite_three
        elif self.specialty_cite_one:
            caption += ", %s" % self.specialty_cite_one
        elif self.state_cite_regional:
            caption += ", %s" % self.state_cite_regional
        elif self.state_cite_one:
            caption += ", %s" % self.state_cite_one
        elif self.westlaw_cite and self.lexis_cite:
            # If both WL and LEXIS
            caption += ", %s, %s" % (self.westlaw_cite, self.lexis_cite)
        elif self.westlaw_cite:
            # If only WL
            caption += ", %s" % self.westlaw_cite
        elif self.lexis_cite:
            # If only LEXIS
            caption += ", %s" % self.lexis_cite
        elif self.docket.docket_number:
            caption += ", %s" % self.docket.docket_number
        caption += ' ('
        if self.docket.court.citation_string != 'SCOTUS':
            caption += re.sub(' ', '&nbsp;', self.docket.court.citation_string)
            caption += '&nbsp;'
            # b/c strftime f's up before 1900.
            caption += '%s)' % self.date_filed.isoformat().split('-')[0]
        return caption

    @property
    def citation_fields(self):
        """The fields that are used for citations, as a list.

        The order of the items in this list follows BlueBook order, so our
        citations aren't just willy nilly.
        """
        return [
            'neutral_cite', 'federal_cite_one', 'federal_cite_two',
            'federal_cite_three', 'scotus_early_cite', 'specialty_cite_one',
            'state_cite_regional', 'state_cite_one', 'state_cite_two',
            'state_cite_three', 'westlaw_cite', 'lexis_cite'
        ]

    @property
    def citation_list(self):
        """Make a citation list

        This function creates a series of citations that can be listed as meta
        data for an opinion.
        """
        return [getattr(self, field) for field in self.citation_fields]

    @property
    def citation_string(self):
        """Make a citation string, joined by commas"""
        return ', '.join([cite for cite in self.citation_list if cite])

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
                [list(sub_opinion.opinions_cited.all().only('pk')) for
                 sub_opinion in
                 self.sub_opinions.all()],
                []
            )
        ).order_by('-citation_count', '-date_filed')

    @property
    def authority_count(self):
        return self.authorities.count()

    @property
    def has_private_authority(self):
        if not hasattr(self, '_has_private_authority'):
            # Calculate it, then cache it.
            private = False
            for authority in self.authorities:
                if authority.blocked:
                    private = True
                    break
            self._has_private_authority = private
        return self._has_private_authority

    def top_visualizations(self):
        return self.visualizations.filter(
            published=True, deleted=False
        ).order_by(
            '-view_count'
        )

    def __unicode__(self):
        if self.case_name:
            return u'%s: %s' % (self.pk, self.case_name)
        else:
            return u'%s' % self.pk

    def get_absolute_url(self):
        return reverse('view_case', args=[self.pk, self.slug])

    def save(self, index=True, force_commit=False, *args, **kwargs):
        self.slug = slugify(trunc(best_case_name(self), 75))
        super(OpinionCluster, self).save(*args, **kwargs)
        if index:
            from cl.search.tasks import add_or_update_cluster
            add_or_update_cluster.delay(self.pk, force_commit)

    def delete(self, *args, **kwargs):
        """
        Note that this doesn't get called when an entire queryset
        is deleted, but that should be OK.
        """
        id_cache = self.pk
        super(OpinionCluster, self).delete(*args, **kwargs)
        from cl.search.tasks import delete_items
        delete_items.delay([id_cache], settings.SOLR_OPINION_URL)


class Opinion(models.Model):
    OPINION_TYPES = (
        ('010combined', 'Combined Opinion'),
        ('020lead', 'Lead Opinion'),
        ('030concurrence', 'Concurrence'),
        ('040dissent', 'Dissent'),
        ('050addendum', 'Addendum'),
    )
    cluster = models.ForeignKey(
        OpinionCluster,
        help_text="The cluster that the opinion is a part of",
        related_name="sub_opinions",
    )
    opinions_cited = models.ManyToManyField(
        'self',
        help_text="Opinions cited by this opinion",
        through='OpinionsCited',
        through_fields=('citing_opinion', 'cited_opinion'),
        symmetrical=False,
        related_name="opinions_citing",
        blank=True,
    )
    author = models.ForeignKey(
        'people_db.Person',
        help_text="The primary author of this opinion as a normalized field",
        related_name='opinions_written',
        blank=True,
        null=True,
    )
    author_str = models.TextField(
        help_text="The primary author of this opinion, as a simple text "
                  "string. This field is used when normalized judges cannot "
                  "be placed into the author field.",
        blank=True,
    )
    per_curiam = models.BooleanField(
        help_text="Is this opinion per curiam, without a single author?",
        default=False,
    )
    joined_by = models.ManyToManyField(
        'people_db.Person',
        related_name='opinions_joined',
        help_text="Other judges that joined the primary author "
                  "in this opinion",
        blank=True,
    )
    date_created = models.DateTimeField(
        help_text="The original creation date for the item",
        auto_now_add=True,
        db_index=True
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified. A value in "
                  "year 1750 indicates the value is unknown",
        auto_now=True,
        db_index=True,
    )
    type = models.CharField(
        max_length=20,
        choices=OPINION_TYPES,
    )
    sha1 = models.CharField(
        help_text="unique ID for the document, as generated via SHA1 of the "
                  "binary file or text data",
        max_length=40,
        db_index=True,
    )
    page_count = models.IntegerField(
        help_text="The number of pages in the document, if known",
        blank=True,
        null=True,
    )
    download_url = models.URLField(
        help_text="The URL on the court website where the document was "
                  "originally scraped",
        max_length=500,
        db_index=True,
        null=True,
        blank=True,
    )
    local_path = models.FileField(
        help_text="The location, relative to MEDIA_ROOT on the CourtListener "
                  "server, where files are stored",
        upload_to=make_upload_path,
        storage=IncrementingFileSystemStorage(),
        blank=True,
        db_index=True
    )
    plain_text = models.TextField(
        help_text="Plain text of the document after extraction using "
                  "pdftotext, wpd2txt, etc.",
        blank=True
    )
    html = models.TextField(
        help_text="HTML of the document, if available in the original",
        blank=True,
        null=True,
    )
    html_lawbox = models.TextField(
        help_text='HTML of Lawbox documents',
        blank=True,
        null=True,
    )
    html_columbia = models.TextField(
        help_text='HTML of Columbia archive',
        blank=True,
        null=True,
    )
    html_with_citations = models.TextField(
        help_text="HTML of the document with citation links and other "
                  "post-processed markup added",
        blank=True
    )
    extracted_by_ocr = models.BooleanField(
        help_text='Whether OCR was used to get this document content',
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
                pk=getattr(self, 'pk', None),
                cn=self.cluster.case_name,
            )
        except AttributeError:
            return u'Orphan opinion with ID: %s' % self.pk

    def get_absolute_url(self):
        return reverse('view_case', args=[self.cluster.pk, self.cluster.slug])

    def clean(self):
        if self.type == '':
            raise ValidationError("'type' is a required field.")

    def save(self, index=True, force_commit=False, *args, **kwargs):
        super(Opinion, self).save(*args, **kwargs)
        if index:
            from cl.search.tasks import add_or_update_opinions
            add_or_update_opinions.delay([self.pk], force_commit)

    def as_search_dict(self):
        """Create a dict that can be ingested by Solr."""
        # IDs
        out = {
            'id': self.pk,
            'docket_id': self.cluster.docket.pk,
            'cluster_id': self.cluster.pk,
            'court_id': self.cluster.docket.court.pk
        }

        # Opinion
        out.update({
            'cites': [opinion.pk for opinion in self.opinions_cited.all()],
            'author_id': getattr(self.author, 'pk', None),
            # 'per_curiam': self.per_curiam,
            'joined_by_ids': [judge.pk for judge in self.joined_by.all()],
            'type': self.type,
            'download_url': self.download_url or None,
            'local_path': unicode(self.local_path),
        })

        # Cluster
        out.update({
            'caseName': best_case_name(self.cluster),
            'caseNameShort': self.cluster.case_name_short,
            'sibling_ids': [sibling.pk for sibling in self.siblings.all()],
            'panel_ids': [judge.pk for judge in self.cluster.panel.all()],
            'non_participating_judge_ids': [
                judge.pk for judge in
                self.cluster.non_participating_judges.all()
            ],
            'judge': self.cluster.judges,
            'lexisCite': self.cluster.lexis_cite,
            'citation': [
                cite for cite in
                self.cluster.citation_list if cite],  # Nuke '' and None
            'neutralCite': self.cluster.neutral_cite,
            'scdb_id': self.cluster.scdb_id,
            'source': self.cluster.source,
            'attorney': self.cluster.attorneys,
            'suitNature': self.cluster.nature_of_suit,
            'citeCount': self.cluster.citation_count,
            'status': self.cluster.get_precedential_status_display(),
            'status_exact': self.cluster.get_precedential_status_display(),
        })
        if self.cluster.date_filed is not None:
            out['dateFiled'] = datetime.combine(
                self.cluster.date_filed,
                time()
            )  # Midnight, PST
        try:
            out['absolute_url'] = self.cluster.get_absolute_url()
        except NoReverseMatch:
            raise InvalidDocumentError(
                "Unable to save to index due to missing absolute_url "
                "(court_id: %s, item.pk: %s). Might the court have in_use set "
                "to False?" % (self.cluster.docket.court_id, self.pk)
            )

        # Docket
        docket = {'docketNumber': self.cluster.docket.docket_number}
        if self.cluster.docket.date_argued is not None:
            docket['dateArgued'] = datetime.combine(
                self.cluster.docket.date_argued,
                time(),
            )
        if self.cluster.docket.date_reargued is not None:
            docket['dateReargued'] = datetime.combine(
                self.cluster.docket.date_reargued,
                time(),
            )
        if self.cluster.docket.date_reargument_denied is not None:
            docket['dateReargumentDenied'] = datetime.combine(
                self.cluster.docket.date_reargument_denied,
                time(),
            )
        out.update(docket)

        court = {
            'court': self.cluster.docket.court.full_name,
            'court_citation_string': self.cluster.docket.court.citation_string,
            'court_exact': self.cluster.docket.court_id,  # For faceting
        }
        out.update(court)

        # Load the document text using a template for cleanup and concatenation
        text_template = loader.get_template('indexes/opinion_text.txt')
        out['text'] = text_template.render({
            'item': self,
            'citation_string': self.cluster.citation_string
        }).translate(null_map)

        return normalize_search_dicts(out)


class OpinionsCited(models.Model):
    citing_opinion = models.ForeignKey(
        Opinion,
        related_name='cited_opinions',
    )
    cited_opinion = models.ForeignKey(
        Opinion,
        related_name='citing_opinions',
    )
    #  depth = models.IntegerField(
    #      help_text='The number of times the cited opinion was cited '
    #                'in the citing opinion',
    #      default=1,
    #      db_index=True,
    #  )
    #  quoted = models.BooleanField(
    #      help_text='Equals true if previous case was quoted directly',
    #      default=False,
    #      db_index=True,
    #  )
    # treatment: positive, negative, etc.
    #

    def __unicode__(self):
        return u'%s ⤜--cites⟶  %s' % (
            self.citing_opinion.id, self.cited_opinion.id)

    class Meta:
        verbose_name_plural = 'Opinions cited'
        unique_together = ("citing_opinion", "cited_opinion")


class Tag(models.Model):
    date_created = models.DateTimeField(
        help_text="The original creation date for the item",
        auto_now_add=True,
        db_index=True
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified. A value in "
                  "year 1750 indicates the value is unknown",
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
        return u'%s: %s' % (self.pk, self.name)


# class AppellateReview(models.Model):
#     REVIEW_STANDARDS = (
#         ('d', 'Discretionary'),
#         ('m', 'Mandatory'),
#         ('s', 'Special or Mixed'),
#     )
#     upper_court = models.ForeignKey(
#         Court,
#         related_name='lower_courts_reviewed',
#     )
#     lower_court = models.ForeignKey(
#         Court,
#         related_name='reviewed_by',
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
