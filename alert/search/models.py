# This software and any associated files are copyright 2010 Brian Carver and
# Michael Lissner.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from alert import settings
from alert.lib.string_utils import trunc

# Celery requires imports like this. Disregard syntax error.
#from search.tasks import delete_docs
#from search.tasks import add_or_update_docs

from alert.tinyurl.encode_decode import num_to_ascii
from django.template.defaultfilters import slugify
from django.utils.text import get_valid_filename
from django.utils.encoding import smart_unicode
from django.db import models
import glob
import os

# changes here need to be mirrored in the coverage page view and Solr configs
# Note that spaces cannot be used in the keys, or else the SearchForm won't work
JURISDICTIONS = (
    ('F', 'Federal'),
    ('S', 'State'),
)

DOCUMENT_STATUSES = (
    ('Published', 'Precedential'),
    ('Unpublished', 'Non-Precedential'),
    ('Errata', 'Errata'),
    ('In-chambers', 'In-chambers'),
    ('Relating-to', 'Relating-to orders'),
)

DOCUMENT_SOURCES = (
    ('C', 'court website'),
    ('R', 'resource.org'),
    ('CR', 'court website merged with resource.org'),
    ('M', 'manual input'),
    ('A', 'internet archive'),
)


def make_pdf_upload_path(instance, filename):
    """Return a string like pdf/2010/08/13/foo_v._var.pdf, with the date set
    as the dateFiled for the case."""
    # this code NOT cross platform. Use os.path.join or similar to fix.
    mimetype = filename.split('.')[-1] + '/'

    try:
        path = mimetype + instance.dateFiled.strftime("%Y/%m/%d/") + \
            get_valid_filename(filename)
    except AttributeError:
        # The date is unknown for the case. Use today's date.
        path = mimetype + instance.time_retrieved.strftime("%Y/%m/%d/") + \
            get_valid_filename(filename)
    return path


def invalidate_dumps_by_date_and_court(date, court):
    '''Deletes dump files for a court and date

    Receives court and date parameters, and then deletes any corresponding
    dumps.
    '''
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
    '''A class to represent some information about each court, can be extended
    as needed.'''
    courtUUID = models.CharField("a unique ID for each court as used in URLs",
                                 max_length=6,
                                 primary_key=True)
    in_use = models.BooleanField('this court is in use in CourtListener',
                                 default=False)
    position = models.FloatField('a float that can be used to order the courts',
                                 null=True,
                                 db_index=True,
                                 unique=True)
    citation_string = models.CharField("the citation abbreviation for the court",
                                  max_length=100,
                                  blank=True)
    short_name = models.CharField('the short name of the court',
                                  max_length=100,
                                  blank=False)
    full_name = models.CharField('the full name of the court',
                                 max_length='200',
                                 blank=False)
    URL = models.URLField("the homepage for each court")
    start_date = models.DateField("the date the court was established",
                                  blank=True,
                                  null=True)
    end_date = models.DateField("the date the court was abolished",
                                blank=True,
                                null=True)
    jurisdiction = models.CharField("the jurisdiction of the court",
                                    max_length=3,
                                    choices=JURISDICTIONS)

    def __unicode__(self):
        return self.full_name

    class Meta:
        db_table = "Court"
        ordering = ["position"]


class Citation(models.Model):
    citationUUID = models.AutoField("a unique ID for each citation",
                                    primary_key=True)
    slug = models.SlugField("URL that the document should map to",
                            max_length=50,
                            null=True)
    case_name = models.TextField("full name of the case",
                                    blank=True)
    docketNumber = models.CharField("the docket number",
                                    max_length=100, # sometimes these are consolidated, hence they need to be long.
                                    blank=True,
                                    null=True)
    westCite = models.CharField("WestLaw citation",
                                max_length=50,
                                blank=True,
                                null=True)
    lexisCite = models.CharField("LexisNexis citation",
                                 max_length=50,
                                 blank=True,
                                 null=True)
    neutral_cite = models.CharField('Neutral citation',
                                      max_length=50,
                                      blank=True,
                                      null=True)

    def save(self, index=True, *args, **kwargs):
        '''
        create the URL from the case name, but only if this is the first
        time it has been saved.
        '''
        created = self.pk is None
        if not self.citationUUID:
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
    '''A class representing a single court opinion.

    This must go last, since it references the above classes
    '''
    documentUUID = models.AutoField("a unique ID for each document",
                                    primary_key=True)
    source = models.CharField(
                      "the source of the document",
                      max_length=3,
                      choices=DOCUMENT_SOURCES,
                      blank=True)
    documentSHA1 = models.CharField(
                      "unique ID for the document, as generated via SHA1 of "
                      "the binary file",
                      max_length=40,
                      db_index=True)
    dateFiled = models.DateField(
                      "the date filed by the court",
                      blank=True,
                      null=True,
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
    time_retrieved = models.DateTimeField(
                      "the exact date and time stamp that the document was "
                      "placed into our database",
                      auto_now_add=True,
                      editable=False,
                      db_index=True)
    local_path = models.FileField(
                      "the location, relative to MEDIA_ROOT, where the files "
                      "are stored",
                      upload_to=make_pdf_upload_path,
                      blank=True,
                      db_index=True)
    documentPlainText = models.TextField(
                      "plain text of the document after extraction",
                      blank=True)
    documentHTML = models.TextField(
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
                      'the number of times this document is cited by other '
                      'cases',
                      default=0)
    documentType = models.CharField(
                      "the precedential status of document",
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

    # source: http://stackoverflow.com/questions/1119722/base-62-conversion-in-python
    def get_small_url(self):
        ascii = num_to_ascii(self.documentUUID)
        return "http://crt.li/x/" + ascii

    def save(self, index=True, *args, **kwargs):
        '''
        If the value of blocked changed to True, invalidate the caches
        where that value was stored. Google can later pick it up properly.
        '''
        # Run the standard save function.
        super(Document, self).save(*args, **kwargs)

        # Update the search index.
        if index:
            # Import is here to avoid looped import problem
            from search.tasks import add_or_update_doc
            add_or_update_doc.delay(self.pk)

        # Delete the cached sitemaps and dumps if the item is blocked.
        if self.blocked:
            invalidate_dumps_by_date_and_court(self.dateFiled, self.court_id)

    def delete(self, *args, **kwargs):
        '''
        If the item is deleted, we need to update the caches that previously
        contained it. Note that this doesn't get called when an entire queryset
        is deleted, but that should be OK.
        '''
        # Delete the item.
        super(Document, self).delete(*args, **kwargs)

        # Update the search index.
        # Import is here to avoid looped import problem
        from search.tasks import delete_doc
        delete_doc.delay(self.pk)

        # Invalidate the sitemap and dump caches
        invalidate_dumps_by_date_and_court(self.dateFiled, self.court_id)

    class Meta:
        db_table = "Document"
