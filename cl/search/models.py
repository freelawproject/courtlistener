# coding=utf-8
import re

from django.core.exceptions import ValidationError
from django.core.urlresolvers import reverse
from django.db import models
from django.utils.encoding import smart_unicode
from django.utils.text import slugify

from cl import settings
from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.lib.model_helpers import make_upload_path
from cl.lib.storage import IncrementingFileSystemStorage
from cl.lib.string_utils import trunc

# changes here need to be mirrored in the coverage page view and Solr configs
# Note that spaces cannot be used in the keys, or else the SearchForm won't work

JURISDICTIONS = (
    ('F',   'Federal Appellate'),
    ('FD',  'Federal District'),
    ('FB',  'Federal Bankruptcy'),
    ('FBP', 'Federal Bankruptcy Panel'),
    ('FS',  'Federal Special'),
    ('S',   'State Supreme'),
    ('SA',  'State Appellate'),
    ('ST',  'State Trial'),
    ('SS',  'State Special'),
    ('C',   'Committee'),
    ('T',   'Testing'),
)

DOCUMENT_STATUSES = (
    ('Published', 'Precedential'),
    ('Unpublished', 'Non-Precedential'),
    ('Errata', 'Errata'),
    ('Memorandum Decision', 'Memorandum Decision'),
    ('Per Curiam Opinion', 'Per Curiam Opinion'),
    ('Separate', 'Separate Opinion'),
    ('Signed Opinion', 'Signed Opinion'),
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


class Docket(models.Model):
    """A class to sit above OpinionClusters and Audio files and link them
    together.
    """
    DEFAULT = 0
    RECAP = 1

    SOURCE_CHOICES = (
        (DEFAULT, "Default"),
        (RECAP, "Recap")
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
    court = models.ForeignKey(
        'Court',
        help_text="The court where the docket was filed",
        db_index=True,
        related_name='dockets',
    )

    assigned_to = models.ForeignKey(
        'judges.Judge',
        help_text="The judge the case was assigned to.",
        null=True
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
        null=True,
    )
    docket_number = models.CharField(
        help_text="The docket numbers of a case, can be consolidated and "
                  "quite long",
        max_length=5000,  # was 50, 100, 300, 1000
        # Docket number is a mandatory field for every Docket object.
        # Setting blank to False makes the field mandatory.
        blank=False,
        null=False,
        db_index=True
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

    date_filed = models.DateField(
        help_text="The date the case was filed.",
        blank=True,
        null=True
    )

    date_terminated = models.DateField(
        help_text="The date the case was terminated.",
        blank=True,
        null=True
    )

    date_last_filing = models.DateField(
        help_text="The date the case was last updated in the docket. ",
        blank=True,
        null=True
    )

    pacer_case_id = models.PositiveIntegerField(
        help_text="The cased ID which PACER provides.",
        # Even though pacer_case_id is a mandatory attribute of RECAP dockets, we cannot have the same here.
        # as existing Dockets in CourtListener don't have pacer_case_number attribute and
        # all Dockets of CourtListener may not be available in RECAP.
        # Therefore pacer_case_id cannot be made a mandatory argument in here.
        null=True,
        blank=True,
        db_index=True
    )

    case_cause = models.CharField(
        help_text=" The type of cause for the case (Not sure)",
        max_length=200,
        null=True,
        blank=True
    )

    nature_of_suit = models.CharField(
        help_text=" The type of case.  (Not sure)",
        max_length=100,
        null=True,
        blank=True
    )

    jury_demand = models.CharField(
        help_text="The compensation demand (Not sure)",
        max_length=500,
        null=True,
        blank=True
    )

    jurisdiction_type = models.CharField(
        help_text="Stands for jurisdiction in RECAP XML docket.",
        # Some examples are : "Diversity", "U.S. Government Defendant",
        max_length=100,
        null=True,
        blank=True
    )

    xml_filepath_local = models.FilePathField(
        help_text="RECAP’s Docket XML page file path in the local storage area.",
        max_length=500,
        null=True,
        blank=True
    )

    xml_filepath_ia = models.FilePathField(
        help_text="The Docket XML page file path in The Internet Archive",
        max_length=500,
        null=True,
        blank=True
    )

    source = models.SmallIntegerField(
        help_text="contains the source of the Docket.",
        null=False,
        blank=False,
        choices=SOURCE_CHOICES,
        default=DEFAULT
    )

    def __unicode__(self):
        if self.case_name:
            return smart_unicode('%s: %s' % (self.pk, self.case_name))
        else:
            return str(self.pk)

    def save(self, *args, **kwargs):
        self.slug = slugify(trunc(best_case_name(self), 75))
        super(Docket, self).save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('view_docket', args=[self.pk, self.slug])


class DocketEntry(models.Model):

    docket = models.ForeignKey(
        Docket,
        null=False,
        blank=False,
        help_text="Foreign key as a relation to the corresponding Docket object. "
                  "Specifies which docket the docket entry belongs to."
    )

    filed_date = models.DateField(
        help_text="The Created date of the Docket Entry.",
        blank=False,
        null=False
    )

    entered_date = models.DateField(
        help_text="The date the Docket entry was entered in RECAP. Found in RECAP.",
        blank=True,
        null=True
    )

    entry_number = models.PositiveIntegerField(
        help_text="# on the PACER docket page.",
        null=False,
        blank=False
        # Here we have made the entry_number a mandatory field because all docket entries in RECAP
        # will and must have an Entry number.
        # RECAP currently does not handle minute entries (Docket entries withoout an entry_number, Discussed in :
        # https://github.com/freelawproject/recap/issues/54)
        # It is also not efficiently possible to handle the order of docket entries without entry_number.
        # Therefore it has to be handled in the RECAP before anything canbe done here.
        # Recap uses the entry_number to identify documents and attachments. Therefore, to maintain the identity of docket
        # entries and documents, it is important to have an entry_number to every docket entry.
    )

    text = models.TextField(
        blank=False,
        null=False,
        help_text="The text content of the docket entry that appears in the PACER docket page. "
                  "This field is the long_desc in RECAP.",
        db_index=True
    )

    def __unicode__(self):
        return "<DocketEntry ---> %s >" % (self.text[:50])


class Document(models.Model):
    """
        The model for Docket Documents and Attachments.
    """

    PACER_DOCUMENT = 1
    ATTACHMENT = 2

    DOCUMENT_TYPES = (
        (PACER_DOCUMENT, "PACER Document"),
        (ATTACHMENT, "Attachment")
    )

    document_type = models.IntegerField(
        help_text="The type of file. Should be an enumeration.(Whether it is a Document or Attachment).",
        null=False,
        blank=False,
        db_index=True,
        choices=DOCUMENT_TYPES
    )

    docket_entry = models.ForeignKey(
        DocketEntry,
        null=False,
        blank=False,
        help_text="Foreign Key to the DocketEntry object to which it belongs. "
                  "Multiple documents can belong to a DocketEntry. (Attachments and Documents together)"
    )

    document_number = models.PositiveIntegerField(
        help_text="If the file is a document, the number is the document_number in RECAP docket.",
        blank=False,
        null=False
    )

    attachment_number = models.PositiveIntegerField(
        help_text="If the file is an attachment, the number is the attachment number in RECAP docket.",
        blank=True,
        null=True
    )

    pacer_doc_id = models.CharField(
        help_text="The ID of the document in PACER. This information is provided by RECAP.",
        max_length=32,  # Same as in RECAP
        null=True,
        blank=True
    )

    date_upload = models.DateTimeField(
        help_text="upload_date in RECAP. The date the file was uploaded to RECAP. This information is provided by RECAP.",
        blank=True,
        null=True
    )

    is_available = models.SmallIntegerField(
        help_text="Boolean (0 or 1) value to say if the document is available in RECAP.",
        blank=True,
        null=True,
        default=0
    )

    free_import = models.SmallIntegerField(
        help_text="Found in RECAP. Says if the document is free.",
        blank=True,
        null=True,
        default=0
    )

    sha1 = models.CharField(
        max_length=40,  # As in RECAP
        blank=True,
        null=True,
        help_text="The ID used for a document in RECAP"
    )

    filepath_local = models.FilePathField(
        help_text=" The path of the file in the local storage area.",
        max_length=500,
        null=False,
        blank=False
    )

    filepath_ia = models.FilePathField(
        help_text=" The URL of the file in IA",
        max_length=500,
        null=False,
        blank=False
    )

    date_created = models.DateTimeField(
        help_text="The date the file was imported to Local Storage.",
        blank=True,
        null=True
    )

    date_modified = models.DateTimeField(
        help_text="The date the Document object was last updated in CourtListener",
        blank=True,
        null=True
    )

    def __unicode__(self):
        return "Docket_%s , document_number_%s , attachment_number_%s" % (self.docket_entry.docket.docket_number, self.document_number, self.attachment_number)
    
    def save(self, *args, **kwargs):
        if self.document_type ==  self.ATTACHMENT:
            if self.attachment_number == None:
                raise ValidationError('attachment_number cannot be null for an attachment.')
        
        super(Document, self).save(*args, **kwargs)


class Court(models.Model):
    """A class to represent some information about each court, can be extended
    as needed."""
    id = models.CharField(
        help_text='a unique ID for each court as used in URLs',
        max_length=15,  # Changes here will require updates in urls.py
        primary_key=True
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
        null=True,
        db_index=True,
        unique=True
    )
    citation_string = models.CharField(
        help_text='the citation abbreviation for the court as dictated by Blue '
                  'Book',
        max_length=100,
        blank=True
    )
    short_name = models.CharField(
        help_text='a short name of the court',
        max_length=100,
        blank=False
    )
    full_name = models.CharField(
        help_text='the full name of the court',
        max_length='200',
        blank=False
    )
    url = models.URLField(
        help_text='the homepage for each court or the closest thing thereto',
        max_length=500,
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
        return self.full_name

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
        'judges.Judge',
        help_text="The judges that heard the oral arguments",
        related_name="opinion_clusters_participating_judges",
        blank=True,
    )
    non_participating_judges = models.ManyToManyField(
        'judges.Judge',
        help_text="The judges that heard the case, but did not participate in "
                  "the opinion",
        related_name="opinion_clusters_non_participating_judges",
        blank=True,
    )
    judges = models.TextField(
        help_text="The judges that heard the oral arguments as a simple text "
                  "string. This field is used when normalized judges cannot "
                  "be placed into the panel field.",
        blank=True,
    )
    per_curiam = models.BooleanField(
        help_text="Was this case heard per curiam?",
        default=False,
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
        help_text="The date filed by the court",
        db_index=True
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
        max_length=50,
        blank=True,
    )
    federal_cite_two = models.CharField(
        help_text="Secondary federal citation",
        max_length=50,
        blank=True,
    )
    federal_cite_three = models.CharField(
        help_text="Tertiary federal citation",
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
        help_text="Lexis Nexus citation (e.g. 1 LEXIS 38237)",
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
            return caption  # neutral cites lack the parentheses, so we're done here.
        elif self.federal_cite_one:
            caption += ", %s" % self.federal_cite_one
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
        caption += '%s)' % self.date_filed.isoformat().split('-')[0]  # b/c strftime f's up before 1900.
        return caption

    @property
    def citation_fields(self):
        """The fields that are used for citations, as a list.

        The order of the items in this list follows BlueBook order, so our
        citations aren't just willy nilly.
        """
        return [
            'neutral_cite', 'federal_cite_one', 'federal_cite_two',
            'federal_cite_three', 'specialty_cite_one', 'state_cite_regional',
            'state_cite_one', 'state_cite_two', 'state_cite_three',
            'westlaw_cite', 'lexis_cite'
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
        'judges.Judge',
        help_text="The primary author of this opinion",
        related_name='opinions_written',
        blank=True,
        null=True,
    )
    joined_by = models.ManyToManyField(
        'judges.Judge',
        related_name='opinions_joined',
        help_text="Other judges that joined the primary author in this opinion",
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
        return self.cluster.sub_opinions

    def __unicode__(self):
        try:
            return "{pk} - {cn}".format(
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


class OpinionsCited(models.Model):
    citing_opinion = models.ForeignKey(
        Opinion,
        related_name='cited_opinions',
    )
    cited_opinion = models.ForeignKey(
        Opinion,
        related_name='citing_opinions',
    )

    def __unicode__(self):
        return u'%s ⤜--cites⟶  %s' % (self.citing_opinion.id,
                                        self.cited_opinion.id)

    class Meta:
        verbose_name_plural = 'Opinions cited'
        unique_together = ("citing_opinion", "cited_opinion")
