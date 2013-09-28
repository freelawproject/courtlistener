from django.db import models
from django.contrib.auth.models import User


class ContactAccountsModel(models.Model):
    user = models.ForeignKey(User, unique=True)
    is_configured = models.BooleanField(default=False)
    google_username = models.CharField(max_length=128)
    google_password = models.CharField(max_length=128)

    def __unicode__(self):
        return self.google_username

