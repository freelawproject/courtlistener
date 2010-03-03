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


from django.db import models

# a tuple, which we'll pass to the choices argument in various places
PACER_CODES = (
    ('ca1',  'United States Court of Appeals for the First Circuit'),
    ('ca2',  'United States Court of Appeals for the Second Circuit'),
    ('ca3',  'United States Third Judicial Circuit'),
    ('ca4',  'United States Fourth Circuit Court of Appeals'),
    ('ca5',  'United States Court of Appeals for the Fifth Circuit'),
    ('ca6',  'United States Court of Appeals for the Sixth Circuit'),
    ('ca7',  'United States 7th Judicial Circuit'),
    ('ca8',  'United States Court of Appeals for the Eighth Circuit'),
    ('ca9',  'United States Court of Appeals for the Ninth Circuit'),
    ('ca10', 'United States Court of Appeals for the Tenth Circuit'),
    ('ca11', 'United States Eleventh Circuit Court of Appeals'),
    ('cadc', 'United States Court of Appeals for the D.C. Circuit'),
    ('cafc', 'United States Court of Appeals for the Federal Circuit'),
)


# A class to represent some information about each court, can be extended as needed.
class Court(models.Model):
    courtUUID = models.CharField("a unique ID for each court", 
        max_length=100,
        primary_key=True, 
        choices=PACER_CODES)
    courtURL = models.URLField("the homepage for each court")
    
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
    court = models.ForeignKey(Court, verbose_name="the court where the judge served")
    canonicalName = models.CharField("the official name of the judge: fname, mname, lname", 
        max_length=150)
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
        
        

# A class which holds the bulk of the information regarding documents. This must 
# go last, since it references the above classes
class Document(models.Model):
    documentSHA1 = models.CharField("unique ID for the document, as generated via sha1 on the PDF", 
        max_length=40, 
        primary_key=True)
    dateFiled = models.DateField("the date filed by the court")
    court = models.ForeignKey(Court, verbose_name="the court where the document was filed")
    judge = models.ManyToManyField(Judge, verbose_name="the judges that heard the case")
    party = models.ManyToManyField(Party, verbose_name="the parties that were in the case")
    download_URL = models.URLField("the URL on the court website where the document was originally scraped", 
        verify_exists=False)
    time_retrieved = models.DateTimeField("the exact date and time stamp that the document was placed into our database", 
        auto_now_add=True, 
        editable=False)
    local_path = models.FileField("the location, relative to MEDIA_ROOT, where the files are stored",
        upload_to='/pdf/%Y/%m/%d')
    documentPlainText = models.TextField("plain text of the document after extraction from the PDF")
    documentType = models.CharField("the type of document, as described by document_types.txt", 
        max_length=50)
        
    def __unicode__(self):
        return self.caseNameShort
        
    class Meta:
        db_table = "Document"
        ordering = ["-time_retrieved"]


# A class, which uses multi-table inheritance to extend the Document model
class Citation(Document):
    caseNameShort = models.CharField("short name, as it is usually found on the court website", 
        max_length=100,
        unique=True)
    caseNameFull =  models.TextField("full name of the case, as found on the first page of the PDF")
    officialCitationWest = models.CharField("the citation number, as described by WestLaw",
        max_length=50)
    officialCitationLexis = models.CharField("the citation number, as described by LexisNexis", max_length=50)
    
    def __unicode__(self):
        return self.caseNameShort
    
    class Meta:
        db_table = "Citation"
        ordering = ["caseNameFull"]


# A class, which uses multi-table inheritance to extend the Document model
class ExcerptSummary(Document):
    autoExcerpt = models.TextField("the first 100 words of the PDF file")
    courtSummary = models.TextField("a summary of the document, as provided by the court itself")

    def __unicode__(self):
        return self.caseNameShort

    class Meta:
        verbose_name = "excerpt summary"
        verbose_name_plural = "excerpt summaries"
        db_table = "ExcerptSummary"
