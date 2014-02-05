from django.db import models
from django.utils.encoding import smart_unicode


class Stat(models.Model):
    name = models.CharField(
        max_length=50,
        db_index=True,
    )
    date_logged = models.DateField(
        db_index=True,
    )
    count = models.IntegerField(

    )

    def __unicode__(self):
        return smart_unicode('%s: %s on %s: %s' % (self.pk, self.name, self.date_logged, self.count))

    class Meta:
        unique_together = ('date_logged', 'name')
