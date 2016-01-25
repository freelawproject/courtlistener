from datetime import timedelta
from decimal import Decimal
from django.db.models import Sum
from django.utils.timezone import now
from django.db import models
from django.contrib.auth.models import User
from localflavor.us import models as local_models

donation_exclusion_codes = [
    1,  # Unknown error
    3,  # Cancelled
    6,  # Failed
    7,  # Reclaimed/Refunded
]


class BarMembership(models.Model):
    barMembership = local_models.USStateField(
        'the two letter state abbreviation of a bar membership'
    )

    def __unicode__(self):
        return self.get_barMembership_display()

    class Meta:
        verbose_name = 'bar membership'
        ordering = ['barMembership']


class UserProfile(models.Model):
    user = models.OneToOneField(
        User,
        related_name='profile',
        verbose_name='the user this model extends',
        unique=True,
    )
    barmembership = models.ManyToManyField(
        BarMembership,
        verbose_name='the bar memberships held by the user',
        blank=True,
    )
    stub_account = models.BooleanField(
        default=False,
    )
    employer = models.CharField(
        "the user's employer",
        max_length=100,
        blank=True,
        null=True,
    )
    address1 = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )
    address2 = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )
    city = models.CharField(
        max_length=50,
        blank=True,
        null=True,
    )
    state = models.CharField(
        max_length=2,
        blank=True,
        null=True,
    )
    zip_code = models.CharField(
        max_length=10,
        blank=True,
        null=True,
    )
    avatar = models.ImageField(
        'the user\'s avatar',
        upload_to='avatars/%Y/%m/%d',
        blank=True,
    )
    wants_newsletter = models.BooleanField(
        'This user wants newsletters',
        default=False,
    )
    plaintext_preferred = models.BooleanField(
        'should the alert should be sent in plaintext',
        default=False,
    )
    activation_key = models.CharField(
        max_length=40,
    )
    key_expires = models.DateTimeField(
        'The time and date when the user\'s activation_key expires',
        blank=True,
        null=True,
    )
    email_confirmed = models.BooleanField(
        'The user has confirmed their email address',
        default=False,
    )

    @property
    def total_donated_last_year(self):
        one_year_ago = now() - timedelta(days=365)
        total = self.user.donations.filter(
            date_created__gte=one_year_ago,
        ).exclude(
            status__in=donation_exclusion_codes,
        ).aggregate(Sum('amount'))['amount__sum']
        if total is None:
            total = Decimal(0.0)
        return total

    @property
    def total_donated(self):
        total = self.user.donations.exclude(
            status__in=donation_exclusion_codes
        ).aggregate(Sum('amount'))['amount__sum']
        if total is None:
            total = Decimal(0.0)
        return total

    def __unicode__(self):
        return u"{name}".format(self.user.username)

    class Meta:
        verbose_name = 'user profile'
        verbose_name_plural = 'user profiles'
