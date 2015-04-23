from django.contrib.auth.models import User
from django.core.validators import MaxLengthValidator
from django.db import models
from cl.audio.models import Audio
from cl.search.models import OpinionCluster


class Favorite(models.Model):
    user = models.ForeignKey(
        User,
        help_text="The user that owns the favorite",
        related_name="favorites",
    )
    cluster_id = models.ForeignKey(
        OpinionCluster,
        verbose_name='the opinion cluster that is favorited',
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
        null=True,
    )
    name = models.CharField(
        'a name for the alert',
        max_length=100,
    )
    notes = models.TextField(
        'notes about the favorite',
        validators=[MaxLengthValidator(500)],
        max_length=500,
        blank=True
    )

    def __unicode__(self):
        return 'Favorite %s' % self.id
