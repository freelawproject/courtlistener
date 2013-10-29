from django.db import models

from alert.search.models import Court


class urlToHash(models.Model):
    """A class to hold URLs and the hash of their contents. This could be added
    to the Court table, except that courts often have more than one URL they
    parse.
    """
    url = models.CharField("the URL that is hashed",
                           max_length=5000,
                           blank=True,
                           editable=False)
    SHA1 = models.CharField("a SHA1 of the court's website HTML",
                            max_length=40,
                            blank=True,
                            editable=False)

    def __unicode__(self):
        return self.url

    class Meta:
        db_table = "urlToHash"
        verbose_name = "URL Hash"
        verbose_name_plural = "URL Hashes"


class ErrorLog(models.Model):
    """A class to hold scraper errors. Items are added by the scraper and
    removed by the scraper's status monitor.
    """
    log_time = models.DateTimeField(
        'the exact date and time of the error',
        auto_now_add=True,
        editable=False,
        null=True)
    log_level = models.CharField(
        'the loglevel of the error encountered',
        max_length=15,
        editable=False)
    court = models.ForeignKey(
        Court,
        verbose_name='the court where the document was filed')
    message = models.TextField(
        'the message produced in the log',
        blank=True,
        editable=False)

    def __unicode__(self):
        return "%s - %s@%s %s" % (self.log_time,
                                  self.log_level,
                                  self.court.pk,
                                  self.message)
