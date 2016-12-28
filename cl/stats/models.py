from django.contrib.auth.models import User
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


class Event(models.Model):
    date_created = models.DateTimeField(
        help_text="The moment when the event was logged",
        auto_now_add=True,
    )
    description = models.CharField(
        help_text="A human-readable description of the event",
        max_length=200,
    )
    user = models.ForeignKey(
        User,
        help_text="A user associated with the event.",
        related_name="events",
        null=True,
        blank=True,
    )

    def __unicode__(self):
        return '%s: Event Object' % self.pk
