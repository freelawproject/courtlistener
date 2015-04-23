"""This file contains legacy models that can be used by the mega_migrate
script.
"""
from cl.donate.models import PROVIDERS, PAYMENT_STATUSES

from django.conf import settings
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.core.validators import MaxLengthValidator
from django.db import models

##
# Alerts
##
FREQUENCY = (
    ('rt', 'Real Time'),
    ('dly', 'Daily'),
    ('wly', 'Weekly'),
    ('mly', 'Monthly'),
    ('off', 'Off'),
)

ITEM_TYPES = (
    ('o', 'Opinion'),
    ('oa', 'Oral Argument'),
)


class Alert(models.Model):
    name = models.CharField(
        verbose_name='a name for the alert',
        max_length=75
    )
    query = models.CharField(
        verbose_name='the text of an alert created by a user',
        max_length=2500
    )
    rate = models.CharField(
        verbose_name='the rate chosen by the user for the alert',
        choices=FREQUENCY,
        max_length=10
    )
    always_send_email = models.BooleanField(
        verbose_name='Always send an alert?',
        default=False
    )
    date_last_hit = models.DateTimeField(
        verbose_name='time of last trigger',
        blank=True,
        null=True
    )

    def __unicode__(self):
        return u'Alert %s: %s' % (self.pk, self.name)

    class Meta:
        verbose_name = 'alert'
        ordering = ['rate', 'query']
        db_table = 'Alert'
        managed = False


class RealTimeQueue(models.Model):
    date_modified = models.DateTimeField(
        help_text='the last moment when the item was modified',
        auto_now=True,
        editable=False,
        db_index=True,
    )
    item_type = models.CharField(
        help_text='the type of item this is, one of: %s' %
                  ', '.join(['%s (%s)' % (t[0], t[1]) for t in ITEM_TYPES]),
        max_length=3,
        choices=ITEM_TYPES,
        db_index=True,
    )
    item_pk = models.IntegerField(
        help_text='the pk of the item',
    )

    class Meta:
        db_table = 'alerts_realtimequeue'
        managed = False


class Favorite(models.Model):
    doc_id = models.ForeignKey(
        "Document",
        verbose_name='the document that is favorited',
        null=True,
        blank=True,
    )
    audio_id = models.ForeignKey(
        "Audio",
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


class Donation(models.Model):
    date_modified = models.DateTimeField(
        auto_now=True,
        editable=False,
        db_index=True,
    )
    date_created = models.DateTimeField(
        auto_now_add=True,
        editable=False,
        db_index=True
    )
    clearing_date = models.DateTimeField(
        null=True,
        blank=True,
    )
    send_annual_reminder = models.BooleanField(
        'Send me a reminder to donate again in one year',
        default=False,
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=None,
    )
    payment_provider = models.CharField(
        max_length=50,
        choices=PROVIDERS,
        default=None,
    )
    payment_id = models.CharField(
        'Internal ID used during a transaction',
        max_length=64,
    )
    transaction_id = models.CharField(
        max_length=64,
        null=True,
        blank=True,
    )
    status = models.SmallIntegerField(
        max_length=2,
        choices=PAYMENT_STATUSES,
    )
    referrer = models.TextField(
        'GET or HTTP referrer',
        blank=True,
    )

    def __unicode__(self):
        return '%s: $%s, %s' % (
            self.get_payment_provider_display(),
            self.amount,
            self.get_status_display()
        )

    class Meta:
        ordering = ['-date_created']
        db_table = "donate_donation"

##
# Search
##
from cl.lib.model_helpers import make_upload_path
from cl.search.models import SOURCES, DOCUMENT_STATUSES, JURISDICTIONS
from django.utils.encoding import smart_unicode


class Court(models.Model):
    """A class to represent some information about each court, can be extended
    as needed."""
    id = models.CharField(
        help_text='a unique ID for each court as used in URLs',
        max_length=15,
        primary_key=True
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified",
        auto_now=True,
        editable=False,
        db_index=True,
        null=True
    )
    in_use = models.BooleanField(
        help_text='Whether this jurisdiction is in use in CourtListener -- increasingly True',
        default=False
    )
    has_opinion_scraper = models.BooleanField(
        help_text='Whether the jurisdiction has a scraper that obtains opinions automatically.',
        default=False,
    )
    has_oral_argument_scraper = models.BooleanField(
        help_text='Whather the jurisdiction has a scraper that obtains oral arguments automatically.',
        default=False,
    )
    position = models.FloatField(
        help_text='A dewey-decimal-style numeral indicating a hierarchical ordering of jurisdictions',
        null=True,
        db_index=True,
        unique=True
    )
    citation_string = models.CharField(
        help_text='the citation abbreviation for the court as dictated by Blue Book',
        max_length=100,
        blank=True
    )
    short_name = models.CharField(
        help_text='a short name of the court',
        max_length=100,
        blank=False
    )
    full_name = models.CharField(
        help_text='the full name of the court',
        max_length='200',
        blank=False
    )
    url = models.URLField(
        help_text='the homepage for each court or the closest thing thereto',
        max_length=500,
    )
    start_date = models.DateField(
        help_text="the date the court was established, if known",
        blank=True,
        null=True
    )
    end_date = models.DateField(
        help_text="the date the court was abolished, if known",
        blank=True,
        null=True
    )
    jurisdiction = models.CharField(
        help_text='the jurisdiction of the court, one of: %s' %
                  ', '.join(['%s (%s)' % (t[0], t[1]) for t in JURISDICTIONS]),
        max_length=3,
        choices=JURISDICTIONS
    )
    notes = models.TextField(
        help_text="any notes about coverage or anything else (currently very raw)",
        blank=True
    )

    def __unicode__(self):
        return self.full_name

    class Meta:
        db_table = "Court"
        ordering = ["position"]


class Docket(models.Model):
    """A class to sit above Documents and Audio files and link them together"""
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified. A value in "
                  "year 1750 indicates the value is unknown",
        auto_now=True,
        editable=False,
        db_index=True,
        null=True,
    )
    court = models.ForeignKey(
        Court,
        help_text="The court where the docket was filed",
        db_index=True,
        null=True
    )
    case_name = models.TextField(
        help_text="The full name of the case",
        blank=True
    )
    slug = models.SlugField(
        help_text="URL that the document should map to (the slug)",
        max_length=50,
        null=True
    )
    date_blocked = models.DateField(
        help_text="The date that this opinion was blocked from indexing by "
                  "search engines",
        blank=True,
        null=True,
        db_index=True,
    )
    blocked = models.BooleanField(
        help_text="Whether a document should be blocked from indexing by "
                  "search engines",
        db_index=True,
        default=False
    )

    def __unicode__(self):
        if self.case_name:
            return smart_unicode('%s: %s' % (self.pk, self.case_name))
        else:
            return str(self.pk)

    def get_absolute_url(self):
        return reverse('view_docket', args=[self.pk, self.slug])

    class Meta:
        db_table = "search_docket"


class Citation(models.Model):
    slug = models.SlugField(
        help_text="URL that the document should map to (the slug)",
        max_length=50,
        null=True
    )
    case_name = models.TextField(
        help_text="The full name of the case",
        blank=True
    )
    docket_number = models.CharField(
        help_text="The docket numbers of a case, can be consolidated and quite "
                  "long",
        max_length=5000,
        # sometimes these are consolidated, hence they need to be long (was 50,
        # 100, 300, 1000).
        blank=True,
        null=True
    )
    federal_cite_one = models.CharField(
        help_text="Primary federal citation",
        max_length=50,
        blank=True,
        null=True
    )
    federal_cite_two = models.CharField(
        help_text="Secondary federal citation",
        max_length=50,
        blank=True,
        null=True
    )
    federal_cite_three = models.CharField(
        help_text="Tertiary federal citation",
        max_length=50,
        blank=True,
        null=True
    )
    state_cite_one = models.CharField(
        help_text="Primary state citation",
        max_length=50,
        blank=True,
        null=True
    )
    state_cite_two = models.CharField(
        help_text="Secondary state citation",
        max_length=50,
        blank=True,
        null=True
    )
    state_cite_three = models.CharField(
        help_text="Tertiary state citation",
        max_length=50,
        blank=True,
        null=True
    )
    state_cite_regional = models.CharField(
        help_text="Regional citation",
        max_length=50,
        blank=True,
        null=True
    )
    specialty_cite_one = models.CharField(
        help_text="Specialty citation",
        max_length=50,
        blank=True,
        null=True
    )
    scotus_early_cite = models.CharField(
        help_text="Early SCOTUS citation such as How., Black, Cranch., etc.",
        max_length=50,
        blank=True,
        null=True
    )
    lexis_cite = models.CharField(
        help_text="Lexis Nexus citation (e.g. 1 LEXIS 38237)",
        max_length=50,
        blank=True,
        null=True
    )
    westlaw_cite = models.CharField(
        help_text="WestLaw citation (e.g. 22 WL 238)",
        max_length=50,
        blank=True,
        null=True
    )
    neutral_cite = models.CharField(
        help_text='Neutral citation',
        max_length=50,
        blank=True,
        null=True
    )

    def __unicode__(self):
        if self.case_name:
            return smart_unicode('%s: %s' % (self.pk, self.case_name))
        else:
            return str(self.pk)

    class Meta:
        db_table = "Citation"


class Document(models.Model):
    """A class representing a single court opinion.

    This must go last, since it references the above classes
    """
    time_retrieved = models.DateTimeField(
        help_text="The original creation date for the item",
        auto_now_add=True,
        editable=False,
        db_index=True
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified. A value in "
                  "year 1750 indicates the value is unknown",
        auto_now=True,
        editable=False,
        db_index=True,
        null=True,
    )
    date_filed = models.DateField(
        help_text="The date filed by the court",
        blank=True,
        null=True,
        db_index=True
    )
    source = models.CharField(
        help_text="the source of the document, one of: %s" %
                  ', '.join(['%s (%s)' % (t[0], t[1]) for t in SOURCES]),
        max_length=3,
        choices=SOURCES,
        blank=True
    )
    sha1 = models.CharField(
        help_text="unique ID for the document, as generated via SHA1 of the "
                  "binary file or text data",
        max_length=40,
        db_index=True
    )
    citation = models.ForeignKey(
        Citation,
        help_text="The citation object for the document",
        related_name="parent_documents",
        blank=True,
        null=True
    )
    docket = models.ForeignKey(
        Docket,
        help_text="The docket that the document is a part of",
        related_name="documents",
        blank=True,
        null=True
    )
    download_url = models.URLField(
        help_text="The URL on the court website where the document was "
                  "originally scraped",
        max_length=500,
        db_index=True,
        null=True,
        blank=True,
    )
    local_path = models.FileField(
        help_text="The location, relative to MEDIA_ROOT on the CourtListener "
                  "server, where files are stored",
        upload_to=make_upload_path,
        blank=True,
        db_index=True
    )
    judges = models.TextField(
        help_text="The judges that brought the opinion as a simple text "
                  "string",
        blank=True,
        null=True,
    )
    nature_of_suit = models.TextField(
        help_text="The nature of the suit. For the moment can be codes or "
                  "laws or whatever",
        blank=True
    )
    plain_text = models.TextField(
        help_text="Plain text of the document after extraction using "
                  "pdftotext, wpd2txt, etc.",
        blank=True
    )
    html = models.TextField(
        help_text="HTML of the document, if available in the original",
        blank=True,
        null=True,
    )
    html_lawbox = models.TextField(
        help_text='HTML of lawbox documents',
        blank=True,
        null=True,
    )
    html_with_citations = models.TextField(
        help_text="HTML of the document with citation links and other "
                  "post-processed markup added",
        blank=True
    )
    cases_cited = models.ManyToManyField(
        Citation,
        help_text="Opinions cited by this opinion",
        related_name="citing_opinions",
        blank=True
    )
    citation_count = models.IntegerField(
        help_text='The number of times this document is cited by other '
                  'opinion',
        default=0,
        db_index=True,
    )
    precedential_status = models.CharField(
        help_text='The precedential status of document, one of: '
                  '%s' % ', '.join([t[0] for t in DOCUMENT_STATUSES]),
        max_length=50,
        blank=True,
        choices=DOCUMENT_STATUSES,
        db_index=True,
    )
    date_blocked = models.DateField(
        help_text="The date that this opinion was blocked from indexing by "
                  "search engines",
        blank=True,
        null=True,
        db_index=True,
    )
    blocked = models.BooleanField(
        help_text="Whether a document should be blocked from indexing by "
                  "search engines",
        db_index=True,
        default=False
    )
    extracted_by_ocr = models.BooleanField(
        help_text='Whether OCR was used to get this document content',
        default=False,
        db_index=True,
    )
    is_stub_document = models.BooleanField(
        help_text='Whether this document is a stub or not',
        default=False
    )
    supreme_court_db_id = models.CharField(
        help_text='The ID of the item in the Supreme Court Database',
        max_length=10,
        blank=True,
        null=True,
        db_index=True,
    )

    def __unicode__(self):
        if self.citation:
            return '%s: %s' % (self.pk, self.citation.case_name)
        else:
            return str(self.pk)

    def get_absolute_url(self):
        return reverse('view_case', args=[self.pk, self.citation.slug])

    class Meta:
        db_table = "Document"


##
# Audio
##
class Audio(models.Model):
    """A class representing oral arguments and their associated metadata

    """
    docket = models.ForeignKey(
        Docket,
        help_text="The docket that the oral argument is a part of",
        related_name="audio_files",
        blank=True,
        null=True,
    )
    source = models.CharField(
        help_text="the source of the audio file, one of: %s" %
                  ', '.join(['%s (%s)' % (t[0], t[1]) for t in SOURCES]),
        max_length=3,
        choices=SOURCES,
        blank=True,
    )
    case_name = models.TextField(
        help_text="The full name of the case",
        blank=True,
    )
    docket_number = models.CharField(
        help_text="The docket numbers of a case, can be consolidated and "
                  "quite long",
        max_length=5000,  # (was 50, 100, 300, 1000).
        blank=True,
        null=True,
    )
    judges = models.TextField(
        help_text="The judges that brought the opinion as a simple text "
                  "string",
        blank=True,
        null=True,
    )
    time_retrieved = models.DateTimeField(
        help_text="The original creation date for the item",
        auto_now_add=True,
        editable=False,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified. A value in year"
                  " 1750 indicates the value is unknown",
        auto_now=True,
        editable=False,
        db_index=True,
    )
    date_argued = models.DateField(
        help_text="the date the case was argued",
        blank=True,
        null=True,
        db_index=True,
    )
    sha1 = models.CharField(
        help_text="unique ID for the document, as generated via SHA1 of the "
                  "binary file or text data",
        max_length=40,
        db_index=True,
    )
    download_url = models.URLField(
        help_text="The URL on the court website where the document was "
                  "originally scraped",
        max_length=500,
        db_index=True,
        null=True,
        blank=True,
    )
    local_path_mp3 = models.FileField(
        help_text="The location, relative to MEDIA_ROOT, on the CourtListener "
                  "server, where encoded file is stored",
        upload_to=make_upload_path,
        blank=True,
        db_index=True,
    )
    local_path_original_file = models.FileField(
        help_text="The location, relative to MEDIA_ROOT, on the CourtListener "
                  "server, where the original file is stored",
        upload_to=make_upload_path,
        db_index=True,
    )
    duration = models.SmallIntegerField(
        help_text="the length of the item, in seconds",
        null=True,
    )
    processing_complete = models.BooleanField(
        help_text="Is audio for this item done processing?",
        default=False,
    )
    date_blocked = models.DateField(
        help_text="The date that this opinion was blocked from indexing by "
                  "search engines",
        blank=True,
        null=True,
        db_index=True,
    )
    blocked = models.BooleanField(
        help_text="Should this item be blocked from indexing by "
                  "search engines?",
        db_index=True,
        default=False,
    )

    class Meta:
        ordering = ["-time_retrieved"]
        verbose_name_plural = 'Audio Files'
        db_table = 'audio_audio'

    def __unicode__(self):
        return '%s: %s' % (self.pk, self.case_name)

    def get_absolute_url(self):
        return reverse('view_audio_file', args=[self.pk, self.docket.slug])

    def delete(self, *args, **kwargs):
        """
        Update the index as items are deleted.
        """
        id_cache = self.pk
        super(Audio, self).delete(*args, **kwargs)
        from search.tasks import delete_item

        delete_item.delay(id_cache, settings.SOLR_AUDIO_URL)


##
# UserHandling
##
from localflavor.us import models as local_models


class BarMembership(models.Model):
    barMembership = local_models.USStateField(
        'the two letter state abbreviation of a bar membership'
    )

    def __unicode__(self):
        return self.get_barMembership_display()

    class Meta:
        verbose_name = 'bar membership'
        ordering = ['barMembership']
        db_table = 'BarMembership'

class UserProfile(models.Model):
    user = models.OneToOneField(
        User,
        related_name='profile_legacy',
        verbose_name='the user this model extends',
        unique=True,
    )
    barmembership = models.ManyToManyField(
        BarMembership,
        verbose_name='the bar memberships held by the user',
        blank=True,
    )
    alert = models.ManyToManyField(
        Alert,
        verbose_name='the alerts created by the user',
        blank=True,
        #related_name='user_profile',
    )
    donation = models.ManyToManyField(
        Donation,
        verbose_name='the donations made by the user',
        related_name='user_profile',
        blank=True,
    )
    favorite = models.ManyToManyField(
        Favorite,
        verbose_name='the favorites created by the user',
        related_name='user_profile',
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

    def __unicode__(self):
        return self.user.username

    class Meta:
        verbose_name = 'user profile'
        verbose_name_plural = 'user profiles'
        db_table = 'UserProfile'
