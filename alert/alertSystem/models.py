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

from djangosphinx.models import SphinxSearch
from django.db import models
import alert


# a tuple, which we'll pass to the choices argument in various places
PACER_CODES = (
    ('ca1',  'Court of Appeals for the First Circuit'),
    ('ca2',  'Court of Appeals for the Second Circuit'),
    ('ca3',  'Court of Appeals for the Third Circuit'),
    ('ca4',  'Court of Appeals for the Fourth Circuit'),
    ('ca5',  'Court of Appeals for the Fifth Circuit'),
    ('ca6',  'Court of Appeals for the Sixth Circuit'),
    ('ca7',  'Court of Appeals for the Seventh Circuit'),
    ('ca8',  'Court of Appeals for the Eighth Circuit'),
    ('ca9',  'Court of Appeals for the Ninth Circuit'),
    ('ca10', 'Court of Appeals for the Tenth Circuit'),
    ('ca11', 'Court of Appeals for the Eleventh Circuit'),
    ('cadc', 'Court of Appeals for the D.C. Circuit'),
    ('cafc', 'Court of Appeals for the Federal Circuit'),
    ('scotus', 'Supreme Court of the United States'),
)

# changes here need to be mirrored in the coverage page view and the exceptions 
# list for sphinx
DOCUMENT_STATUSES = (
    ('P', 'Published/Precedential'),
    ('U', 'Unpublished/Non-Precedential'),
    ('E', 'Errata'),
    ('I', 'In-chambers'),
    ('R', 'Relating-to orders'),
)

DOCUMENT_SOURCES = (
    ('C', 'court website'),
    ('R', 'bulk.resource.org'),
    ('M', 'manual input'),
)


# A class to represent some information about each court, can be extended as needed.
class Court(models.Model):
    courtUUID = models.CharField("a unique ID for each court",
        max_length=100,
        primary_key=True,
        choices=PACER_CODES)
    courtURL = models.URLField("the homepage for each court")
    courtShortName = models.CharField("the shortname for the court",
        max_length=100,
        blank=True)

    # uses the choices argument in courtUUID to create a good display of the object.
    def __unicode__(self):
        return self.get_courtUUID_display()

    class Meta:
        db_table = "Court"
        ordering = ["courtUUID"] #this reinforces the default



# A class to represent each party that is extracted from a document
class Party(models.Model):
    partyUUID = models.AutoField("a unique ID for each party", primary_key=True)
    partyExtracted = models.CharField("a party name", max_length=100)

    def __unicode__(self):
        return self.partyExtracted

    class Meta:
        verbose_name_plural = "parties"
        db_table = "Party"
        ordering = ["partyExtracted"]



# A class to represent each judge that is extracted from a document
class Judge(models.Model):
    judgeUUID = models.AutoField("a unique ID for each judge", primary_key=True)
    court = models.ForeignKey(Court, verbose_name="the court where the judge served during this time period")
    canonicalName = models.CharField("the official name of the judge: fname, mname, lname",
        max_length=150)
    judgeAvatar = models.ImageField("the judge's face",
        upload_to="avatars/judges/%Y/%m/%d",
        blank=True)
    startDate = models.DateField("the start date that the judge is on the bench")
    endDate = models.DateField("the end date that the judge is on the bench")

    def __unicode__(self):
        return self.canonicalName

    class Meta:
        db_table = "Judge"
        ordering = ["court", "canonicalName"]


# A class to hold the various aliases that a judge may have, such as M. Lissner,
# Michael Jay Lissner, Michael Lissner, etc.
class JudgeAlias (models.Model):
    aliasUUID = models.AutoField("a unique ID for each alias", primary_key=True)
    judgeUUID = models.ForeignKey(Judge, verbose_name="the judge for whom we are assigning an alias")
    alias = models.CharField("a name under which the judge appears in a document", max_length=100)

    # should return something like 'Mike is mapped to Michael Lissner'
    def __unicode__(self):
        return u'%s is mapped to %s' % (self.alias, self.judgeUUID.canonicalName)

    class Meta:
        verbose_name = "judge alias"
        verbose_name_plural = "judge aliases"
        db_table = "JudgeAlias"
        ordering = ["alias"]



class Citation(models.Model):
    search = SphinxSearch()
    citationUUID = models.AutoField("a unique ID for each citation",
        primary_key=True)
    caseNameShort = models.CharField("short name, as it is usually found on the court website",
        max_length=100,
        blank=True,
        db_index=True)
    caseNameFull =  models.TextField("full name of the case, as found on the first page of the PDF",
        blank=True)
    caseNumber = models.CharField("the case number",
        blank=True,
        max_length=50,
        db_index=True)
    officialCitationWest = models.CharField("the citation number, as described by WestLaw",
        max_length=50,
        blank=True)
    officialCitationLexis = models.CharField("the citation number, as described by LexisNexis",
        max_length=50,
        blank=True)

    def __unicode__(self):
        if self.caseNameShort:
            return self.caseNameShort
        else:
            return self.citationUUID

    class Meta:
        db_table = "Citation"
        ordering = ["caseNameFull"]



class ExcerptSummary(models.Model):
    excerptUUID = models.AutoField("a unique ID for each excerpt",
        primary_key=True)
    autoExcerpt = models.TextField("the first 100 words of the PDF file",
        blank=True)
    courtSummary = models.TextField("a summary of the document, as provided by the court itself",
        blank=True)

    def __unicode__(self):
        return self.excerptUUID

    class Meta:
        verbose_name = "excerpt summary"
        verbose_name_plural = "excerpt summaries"
        db_table = "ExcerptSummary"



# A class which holds the bulk of the information regarding documents. This must
# go last, since it references the above classes
class Document(models.Model):
    search = SphinxSearch()
    documentUUID = models.AutoField("a unique ID for each document",
        primary_key=True)
    source = models.CharField("the source of the document",
        max_length=3,
        choices=DOCUMENT_SOURCES,
        blank=True)
    documentSHA1 = models.CharField("unique ID for the document, as generated via sha1 on the PDF",
        max_length=40,
        db_index=True)
    dateFiled = models.DateField("the date filed by the court",
        blank=True,
        null=True,
        db_index=True)
    court = models.ForeignKey(Court,
        verbose_name="the court where the document was filed",
        db_index=True)
    judge = models.ManyToManyField(Judge,
        verbose_name="the judges that heard the case",
        blank=True,
        null=True)
    party = models.ManyToManyField(Party,
        verbose_name="the parties that were in the case",
        blank=True,
        null=True)
    citation = models.ForeignKey(Citation,
        verbose_name="the citation information for the document",
        blank=True,
        null=True)
    excerptSummary = models.ForeignKey(ExcerptSummary,
        verbose_name="the excerpt information for the document",
        blank=True,
        null=True)
    download_URL = models.URLField("the URL on the court website where the document was originally scraped",
        verify_exists=False)
    time_retrieved = models.DateTimeField("the exact date and time stamp that the document was placed into our database",
        auto_now_add=True,
        editable=False)
    local_path = models.FileField("the location, relative to MEDIA_ROOT, where the files are stored",
        upload_to='pdf/%Y/%m/%d',
        blank=True)
    documentPlainText = models.TextField("plain text of the document after extraction from the PDF",
        blank=True)
    documentHTML = models.TextField("HTML of the document",
        blank=True)
    documentType = models.CharField("the type of document, as described by document_types.txt",
        max_length=50,
        blank=True,
        choices=DOCUMENT_STATUSES)

    def __unicode__(self):
        if self.citation:
            return self.citation.caseNameShort
        else:
            return self.documentSHA1

    @models.permalink
    def get_absolute_url(self):
        try:
            return ('viewCases', [str(self.court.courtUUID),
                str(self.citation.caseNameShort).replace('-', '_').replace(' ', '-')])
        except:
            return ('viewCases', [str(self.court.courtUUID),
                str(self.documentSHA1)])

    class Meta:
        db_table = "Document"
        ordering = ["-time_retrieved"]
