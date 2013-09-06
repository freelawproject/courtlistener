from django.core.validators import MaxLengthValidator
from django.db import models
from alert.search.models import Document


class Favorite(models.Model):
    doc_id = models.ForeignKey(
        Document,
        verbose_name='the document that is favorited'
    )
    name = models.CharField(
        'a name for the alert', max_length=100
    )
    notes = models.TextField(
        'notes about the favorite',
        validators=[MaxLengthValidator(500)],
        max_length=500,
        blank=True
    )

    def __unicode__(self):
        return 'Favorite %s' % self.id

    class Meta:
        db_table = 'Favorite'
