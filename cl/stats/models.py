from django.contrib.auth.models import User
from django.db import models


class Event(models.Model):
    date_created = models.DateTimeField(
        help_text="The moment when the event was logged", auto_now_add=True
    )
    description = models.CharField(
        help_text="A human-readable description of the event", max_length=200
    )
    user = models.ForeignKey(
        User,
        help_text="A user associated with the event.",
        related_name="events",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )

    def __str__(self) -> str:
        return f"{self.pk}: Event Object"
