from alert import settings
from alert.lib.string_utils import trunc
from alert.lib.encode_decode import num_to_ascii

from django.template.defaultfilters import slugify
from django.utils.text import get_valid_filename
from django.utils.encoding import smart_unicode
from django.db import models
import os

# changes here need to be mirrored in the coverage page view and Solr configs
# Note that spaces cannot be used in the keys, or else the SearchForm won't work
JURISDICTIONS = (
    ('F', 'Federal'),
    ('FB', 'Federal Bankruptcy'),
    ('FD', 'Federal District'),
    ('FS', 'Federal Special'),
    ('S', 'State Supreme'),
    ('SA', 'State Appellate'),
    ('SS', 'State Special'),
    ('C', 'Committee'),
    ('T', 'Testing'),
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

DOCUMENT_SOURCES = (
    ('C', 'court website'),
    ('R', 'resource.org'),
    ('CR', 'court website merged with resource.org'),
    ('LB', 'lawbox'),
    ('LBM', 'lawbox merged with court'),
    ('LBRM', 'lawbox merged with resource.org'),
    ('M', 'manual input'),
    ('A', 'internet archive'),
)


def make_upload_path(instance, filename):
    """Return a string like pdf/2010/08/13/foo_v._var.pdf, with the date set
    as the date_filed for the case."""
    # this code NOT cross platform. Use os.path.join or similar to fix.
    mimetype = filename.split('.')[-1] + '/'

    try:
        path = mimetype + instance.date_filed.strftime("%Y/%m/%d/") + \
            get_valid_filename(filename)
    except AttributeError:
        # The date is unknown for the case. Use today's date.
        path = mimetype + instance.time_retrieved.strftime("%Y/%m/%d/") + \
            get_valid_filename(filename)
    return path


def invalidate_dumps_by_date_and_court(date, court):
    """Deletes dump files for a court and date

    Receives court and date parameters, and then deletes any corresponding
    dumps.
    """
    year, month, day = '%s' % date.year, '%02d' % date.month, '%02d' % date.day
    courts = (court, 'all')
    for court in courts:
        try:
            os.remove(os.path.join(settings.DUMP_DIR, year, court + '.xml.gz'))
        except OSError:
            pass
        try:
            os.remove(os.path.join(settings.DUMP_DIR, year, month, court + '.xml.gz'))
        except OSError:
            pass
        try:
            os.remove(os.path.join(settings.DUMP_DIR, year, month, day, court + '.xml.gz'))
        except OSError:
            pass


class Court(models.Model):
    """A class to represent some information about each court, can be extended
    as needed."""
    courtUUID = models.CharField(
        'a unique ID for each court as used in URLs',
        max_length=15,
        primary_key=True)
    date_modified = models.DateTimeField(
        auto_now=True,
        editable=False,
        db_index=True,
        null=True)
    in_use = models.BooleanField(
        'this court is in use in CourtListener',
        default=False)
    position = models.FloatField(
        null=True,
        db_index=True,
        unique=True)
    citation_string = models.CharField(
        'the citation abbreviation for the court',
        max_length=100,
        blank=True)
    short_name = models.CharField(
        'the short name of the court',
        max_length=100,
        blank=False)
    full_name = models.CharField(
        'the full name of the court',
        max_length='200',
        blank=False)
    URL = models.URLField('the homepage for each court')
    start_date = models.DateField(
        "the date the court was established",
        blank=True,
        null=True)
    end_date = models.DateField(
        "the date the court was abolished",
        blank=True,
        null=True)
    jurisdiction = models.CharField(
        "the jurisdiction of the court",
        max_length=3,
        choices=JURISDICTIONS)
    notes = models.TextField(
        "any notes about coverage or anything else",
        blank=True)

    def __unicode__(self):
        return self.full_name

    class Meta:
        db_table = "Court"
        ordering = ["position"]


class Citation(models.Model):
    citationUUID = models.AutoField(
        "a unique ID for each citation",
        primary_key=True)
    slug = models.SlugField(
        "URL that the document should map to (the slug)",
        max_length=50,
        null=True)
    case_name = models.TextField(
        "full name of the case",
        blank=True)
    docket_number = models.CharField(
        "the docket number",
        max_length=100, # sometimes these are consolidated, hence they need to be long.
        blank=True,
        null=True)
    federal_cite_one = models.CharField(
        "Primary federal citation",
        max_length=50,
        blank=True,
        null=True)
    federal_cite_two = models.CharField(
        "Secondary federal citation",
        max_length=50,
        blank=True,
        null=True)
    federal_cite_three = models.CharField(
        "Tertiary federal citation",
        max_length=50,
        blank=True,
        null=True)
    state_cite_one = models.CharField(
        "Primary state citation",
        max_length=50,
        blank=True,
        null=True)
    state_cite_two = models.CharField(
        "Secondary state citation",
        max_length=50,
        blank=True,
        null=True)
    state_cite_three = models.CharField(
        "Tertiary state citation",
        max_length=50,
        blank=True,
        null=True)
    state_cite_regional = models.CharField(
        "Regional citation",
        max_length=50,
        blank=True,
        null=True)
    specialty_cite_one = models.CharField(
        "Specialty citation",
        max_length=50,
        blank=True,
        null=True)
    scotus_early_cite = models.CharField(
        "Early SCOTUS citation",
        max_length=50,
        blank=True,
        null=True)
    lexis_cite = models.CharField(
        "Lexis Nexus citation (e.g. 1 LEXIS 38237)",
        max_length=50,
        blank=True,
        null=True)
    westlaw_cite = models.CharField(
        "WestLaw citation (e.g. 22 WL 238)",
        max_length=50,
        blank=True,
        null=True)
    neutral_cite = models.CharField(
        'Neutral citation',
        max_length=50,
        blank=True,
        null=True)

    def save(self, index=True, *args, **kwargs):
        """
        create the URL from the case name, but only if this is the first
        time it has been saved.
        """
        created = self.pk is None
        if created:
            # it's the first time it has been saved; generate the slug stuff
            self.slug = trunc(slugify(self.case_name), 50)
        super(Citation, self).save(*args, **kwargs)

        # We only do this on update, not creation
        if index and not created:
            # Import is here to avoid looped import problem
            from search.tasks import update_cite
            update_cite.delay(self.pk)

    def __unicode__(self):
        if self.case_name:
            return smart_unicode(self.case_name)
        else:
            return str(self.citationUUID)

    class Meta:
        db_table = "Citation"


class Document(models.Model):
    """A class representing a single court opinion.

    This must go last, since it references the above classes
    """
    documentUUID = models.AutoField(
        "a unique ID for each document",
        primary_key=True)
    time_retrieved = models.DateTimeField(
        "the original creation date for the item",
        auto_now_add=True,
        editable=False,
        db_index=True)
    date_modified = models.DateTimeField(
        auto_now=True,
        editable=False,
        db_index=True,
        null=True)
    date_filed = models.DateField(
        "the date filed by the court",
        blank=True,
        null=True,
        db_index=True)
    source = models.CharField(
        "the source of the document",
        max_length=3,
        choices=DOCUMENT_SOURCES,
        blank=True)
    sha1 = models.CharField(
        "unique ID for the document, as generated via SHA1 of "
        "the binary file",
        max_length=40,
        db_index=True)
    court = models.ForeignKey(
        Court,
        verbose_name="the court where the document was filed",
        db_index=True)
    citation = models.ForeignKey(
        Citation,
        verbose_name="the citation information for the document",
        blank=True,
        null=True)
    download_URL = models.URLField(
        "the URL on the court website where the document was "
        "originally scraped",
        verify_exists=False,
        db_index=True)
    local_path = models.FileField(
        "the location, relative to MEDIA_ROOT, where the files are stored",
        upload_to=make_upload_path,
        blank=True,
        db_index=True)
    judges = models.TextField(
        "the judges that brought the opinion",
        blank=True)
    nature_of_suit = models.TextField(
        "the nature of the suit, can be codes or laws or whatever",
        blank=True)
    plain_text = models.TextField(
        "plain text of the document after extraction",
        blank=True)
    html = models.TextField(
        "HTML of the document",
        blank=True)
    html_with_citations = models.TextField(
        "HTML of the document with citation links",
        blank=True)
    cases_cited = models.ManyToManyField(
        Citation,
        related_name="citing_cases",
        verbose_name="Cases cited (do not update!)",
        null=True,
        blank=True)
    citation_count = models.IntegerField(
        'the number of times this document is cited by other cases',
        default=0)
    precedential_status = models.CharField(
        'the precedential status of document',
        max_length=50,
        blank=True,
        choices=DOCUMENT_STATUSES)
    date_blocked = models.DateField(
        'original block date',
        blank=True,
        null=True)
    blocked = models.BooleanField(
        'block indexing of this document',
        db_index=True,
        default=False)
    extracted_by_ocr = models.BooleanField(
        'OCR was used to get this document content',
        default=False)

    def __unicode__(self):
        if self.citation:
            return self.citation.case_name
        else:
            return str(self.documentUUID)

    @models.permalink
    def get_absolute_url(self):
        return ('view_case',
                [str(self.court.courtUUID),
                 num_to_ascii(self.documentUUID),
                 self.citation.slug])

    def save(self, index=True, *args, **kwargs):
        """
        If the value of blocked changed to True, invalidate the caches
        where that value was stored. Google can later pick it up properly.
        """
        # Run the standard save function.
        super(Document, self).save(*args, **kwargs)

        # Update the search index.
        if index:
            # Import is here to avoid looped import problem
            from search.tasks import add_or_update_doc
            add_or_update_doc.delay(self.pk)

        # Delete the cached sitemaps and dumps if the item is blocked.
        if self.blocked:
            invalidate_dumps_by_date_and_court(self.date_filed, self.court_id)

    def delete(self, *args, **kwargs):
        """
        If the item is deleted, we need to update the caches that previously
        contained it. Note that this doesn't get called when an entire queryset
        is deleted, but that should be OK.
        """
        # Get the ID for later use
        doc_id_was = self.pk

        # Delete the item from the DB.
        super(Document, self).delete(*args, **kwargs)

        # Update the search index.
        # Import is here to avoid looped import problem
        from search.tasks import delete_doc
        delete_doc.delay(doc_id_was)

        # Invalidate the sitemap and dump caches
        if self.date_filed:
            invalidate_dumps_by_date_and_court(self.date_filed, self.court_id)

    class Meta:
        db_table = "Document"
