from django.db import models
from alert.alertSystem.models import *

class UrlMapper(models.Model):
    # a class to map custom urls to Document objects
    url = models.SlugField("URL that the document should map to",
        max_length = 50,
        db_index   = True,
        editable   = False)
    '''
    document = models.ForeignKey(Document,
        verbose_name="the document the URL points to",
        blank=False,
        null=False)'''



'''
Design:
    - the slug field is populated using the citation information that is affiliated with a Document and the slugify function.
    - the slug must be unique_together with Document.citation.casename and Document.court
    - the slug gets created when Documents are saved, so we need a save function...however, they should not ever change (editable = False)
    -

Notes:
    - use slugify to create URLs
    - investigate prepopulated_fields: http://docs.djangoproject.com/en/dev/ref/contrib/admin/#django.contrib.admin.ModelAdmin.prepopulated_fields
    - use something here to make unique slugs http://djangosnippets.org/tags/slug/ (or, I can do it myself, but I need to make sure
      that I respect the max_length field.)
    -
'''

'''
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
        if self.canonicalName:
            return self.canonicalName
        else:
            return str(self.judgeUUID)

    class Meta:
        db_table = "Judge"
        ordering = ["court", "canonicalName"]
'''
