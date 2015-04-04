from django.core.validators import MaxLengthValidator
from django.db import models
from alert.audio.models import Audio
from alert.search.models import Document


class Favorite(models.Model):
    doc_id = models.ForeignKey(
        Document,
        verbose_name='the document that is favorited',
        null=True,
        blank=True,
    )
    audio_id = models.ForeignKey(
        Audio,
        verbose_name='the audio file that is favorited',
        null=True,
        blank=True,
    )
    date_modified = models.DateTimeField(
        auto_now=True,
        editable=False,
        db_index=True,
        null=True
    )
    name = models.CharField(
        'a name for the alert',
        max_length=100
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
