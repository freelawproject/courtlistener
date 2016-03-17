from django.core.exceptions import ValidationError
from django.core.urlresolvers import reverse
from django.db import models
from django.utils.text import slugify
from localflavor.us import models as local_models
from cl.lib.model_helpers import validate_partial_date
from cl.lib.string_utils import trunc
from cl.search.models import Court

SUFFIXES = (
    ('jr', 'Jr.'),
    ('sr', 'Sr.'),
    ('1', 'I'),
    ('2', 'II'),
    ('3', 'III'),
    ('4', 'IV'),
)
GENDERS = (
    ('m', 'Male'),
    ('f', 'Female'),
    ('o', 'Other'),
)
GRANULARITY_YEAR = '%Y'
GRANULARITY_MONTH = '%Y-%m'
GRANULARITY_DAY = '%Y-%m-%d'
DATE_GRANULARITIES = (
    (GRANULARITY_YEAR, 'Year'),
    (GRANULARITY_MONTH, 'Month'),
    (GRANULARITY_DAY, 'Day'),
)


class Person(models.Model):
    race = models.ManyToManyField(
        'Race',
        blank=True,
    )
    is_alias_of = models.ForeignKey(
        'self',
        blank=True,
        null=True,
    )
    date_created = models.DateTimeField(
        help_text="The original creation date for the item",
        auto_now_add=True,
        db_index=True
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified.",
        auto_now=True,
        db_index=True,
    )
    fjc_id = models.IntegerField(
        help_text="The ID of a judge as assigned by the Federal Judicial "
                  "Center.",
        null=True,
        blank=True,
        unique=True,
        db_index=True,
    )
    slug = models.SlugField(
        max_length=158  # len(self.name_full)
    )
    name_first = models.CharField(
        max_length=50,
    )
    name_middle = models.CharField(
        max_length=50,
        blank=True,
    )
    name_last = models.CharField(
        max_length=50,
        db_index=True,
    )
    name_suffix = models.CharField(
        choices=SUFFIXES,
        max_length=5,
        blank=True,
    )
    date_dob = models.DateField(
        null=True,
        blank=True,
    )
    date_granularity_dob = models.CharField(
        choices=DATE_GRANULARITIES,
        max_length=15,
        blank=True,
    )
    date_dod = models.DateField(
        null=True,
        blank=True,
    )
    date_granularity_dod = models.CharField(
        choices=DATE_GRANULARITIES,
        max_length=15,
        blank=True,
    )
    dob_city = models.CharField(
        max_length=50,
        blank=True,
    )
    dob_state = local_models.USStateField(
        blank=True,
    )
    dod_city = models.CharField(
        max_length=50,
        blank=True,
    )
    dod_state = local_models.USStateField(
        blank=True,
    )
    gender = models.CharField(
        choices=GENDERS,
        max_length=2,
    )

    def __unicode__(self):
        return u'%s: %s' % (self.pk, ' '.join([self.name_first,
                                               self.name_middle,
                                               self.name_last,
                                               self.name_suffix]))

    def get_absolute_url(self):
        return reverse('view_judge', args=[self.pk, self.slug])

    def save(self, *args, **kwargs):
        self.slug = slugify(
            trunc('%s %s %s %s' % (self.name_first, self.name_middle,
                                   self.name_last, self.name_suffix),
                  158),
        )
        self.full_clean()
        super(Person, self).save(*args, **kwargs)

    def clean_fields(self, *args, **kwargs):
        for field in ['dob', 'dod']:
            validate_partial_date(self, field)
        super(Person, self).clean_fields(*args, **kwargs)

    @property
    def name_full(self):
        return ' '.join([
            self.name_first,
            self.name_middle,
            self.name_last,
            self.name_suffix,
        ])

    class Meta:
        verbose_name_plural = "people"


class School(models.Model):
    is_alias_of = models.ForeignKey(
        'self',
        blank=True,
        null=True,
    )
    date_created = models.DateTimeField(
        help_text="The original creation date for the item",
        auto_now_add=True,
        db_index=True
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified",
        auto_now=True,
        db_index=True,
    )
    name = models.CharField(
        max_length=120,  # Dept. Ed. bulk data had a max of 91.
        db_index=True,
    )
    ein = models.IntegerField(
        help_text="The EIN assigned by the IRS",
        null=True,
        blank=True,
        db_index=True,
    )

    def __unicode__(self):
        if self.is_alias_of:
            return u'%s: %s (alias: %s)' % (
                self.pk, self.name, self.is_alias_of.name
            )
        else:
            return u'%s: %s' % (
                self.pk, self.name
            )


class Position(models.Model):
    """A role held by a person, and the details about it."""
    POSITION_TYPES = (
        ('Judge', (
            # Acting
            ('act-jud',      'Acting Judge'),
            ('act-pres-jud', 'Acting Presiding Judge'),

            # Associate
            ('ass-jud',      'Associate Judge'),
            ('ass-c-jud',    'Associate Chief Judge'),
            ('ass-pres-jud', 'Associate Presiding Judge'),
            ('jud',          'Judge'),
            ('jus',          'Justice'),

            # Chief
            ('c-jud',     'Chief Judge'),
            ('c-jus',     'Chief Justice'),
            ('pres-jud',  'Presiding Judge'),
            ('pres-jus',  'Presiding Justice'),
            ('pres-mag',  'Presiding Magistrate'),
            # Commissioner
            ('com',     'Commissioner'),
            ('com-dep', 'Deputy Commissioner'),

            # Pro Tem
            ('jud-pt', 'Judge Pro Tem'),
            ('jus-pt', 'Justice Pro Tem'),
            ('mag-pt', 'Magistrate Pro Tem'),

            # Referee
            ('ref-jud-tr',      'Judge Trial Referee'),
            ('ref-off',         'Official Referee'),
            ('ref-state-trial', 'State Trial Referee'),

            # Retired
            ('ret-act-jus',    'Active Retired Justice'),
            ('ret-ass-jud',    'Retired Associate Judge'),
            ('ret-c-jud',      'Retired Chief Judge'),
            ('ret-jus',        'Retired Justice'),
            ('ret-senior-jud', 'Senior Judge'),

            # Special
            ('spec-chair',  'Special Chairman'),
            ('spec-jud',    'Special Judge'),
            ('spec-m',      'Special Master'),
            ('spec-scjcbc', 'Special Superior Court Judge for Complex Business '
                            'Cases'),
            # Other
            ('chair',     'Chairman'),
            ('chan',      'Chancellor'),
            ('mag',       'Magistrate'),
            ('presi-jud', 'President'),
            ('res-jud',   'Reserve Judge'),
            ('trial-jud', 'Trial Judge'),
            ('vice-chan', 'Vice Chancellor'),
            ('vice-cj',   'Vice Chief Judge'),
        )),
        # Sometimes attorney generals write opinions too
        ('Attorney General', (
            ('att-gen',          'Attorney General'),
            ('att-gen-ass',      'Assistant Attorney General'),
            ('att-gen-ass-spec', 'Special Assistant Attorney General'),
            ('sen-counsel',      'Senior Counsel'),
            ('dep-sol-gen',      'Deputy Solicitor General'),
        )),
        ('Appointing Authority', (
            ('pres',          'President'),
            ('gov',           'Governor'),
        )),
        ('Clerkships', (
            ('clerk',      'Clerk'),
            ('staff-atty', 'Staff Attorney'),
        )),

        ('prof',    'Professor'),
        ('prac',    'Practitioner'),
        ('pros',    'Prosecutor'),
        ('pub_def', 'Public Defender'),
        ('legis',   'Legislator'),
    )
    NOMINATION_PROCESSES = (
        ('fed_senate', 'U.S. Senate'),
        ('state_senate', 'State Senate'),
        ('election', 'Primary Election'),
        ('merit_comm', 'Merit Commission'),
    )
    JUDICIAL_COMMITTEE_ACTIONS = (
        ('no_rep', 'Not Reported'),
        ('rep_w_rec', 'Reported with Recommendation'),
        ('rep_wo_rec', 'Reported without Recommendation'),
        ('rec_postpone', 'Recommendation Postponed'),
        ('rec_bad', 'Recommended Unfavorably'),
    )
    SELECTION_METHODS = (
        ('e_part', 'Partisan Election'),
        ('e_non_part', 'Non-Partisan Election'),
        ('a_pres', 'Appointment (President)'),
        ('a_gov', 'Appointment (Governor)'),
        ('a_legis', 'Appointment (Legislature)'),
    )
    TERMINATION_REASONS = (
        ('ded', 'Death'),
        ('retire_vol', 'Voluntary Retirement'),
        ('retire_mand', 'Mandatory Retirement'),
        ('resign', 'Resigned'),
        ('other_pos', 'Appointed to Other Judgeship'),
        ('lost', 'Lost Election'),
        ('abolished', 'Court Abolished'),
        ('bad_judge', 'Impeached and Convicted'),
        ('recess_not_confirmed', 'Recess Appointment Not Confirmed'),
    )
    position_type = models.CharField(
        choices=POSITION_TYPES,
        max_length=20,
        blank=True,
        null=True,
    )
    person = models.ForeignKey(
        Person,
        related_name='positions',
        blank=True,
        null=True,
    )
    court = models.ForeignKey(
        Court,
        related_name='court_positions',
        blank=True,
        null=True,
    )
    appointer = models.ForeignKey(
        Person,
        related_name='appointed_positions',
        help_text="If this is an appointed position, "
                  "the person responsible for the appointing.",
        blank=True,
        null=True,
    )
    supervisor = models.ForeignKey(
        Person,
        related_name='supervised_positions',
        help_text="If this is a clerkship, the supervising judge.",
        blank=True,
        null=True,
    )
    predecessor = models.ForeignKey(
        Person,
        blank=True,
        null=True,
    )
    school = models.ForeignKey(
        School,
        help_text="If academic job, the school where they work.",
        blank=True,
        null=True,
    )
    job_title = models.CharField(
        help_text="If title isn't in list, type here.",
        max_length=100,
        blank=True,
    )
    organization_name = models.CharField(
        help_text="If org isnt court or school, type here.",
        max_length=120,
        blank=True,
        null=True,
    )
    date_created = models.DateTimeField(
        help_text="The time when this item was created",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified.",
        auto_now=True,
        db_index=True,
    )
    date_nominated = models.DateField(
        help_text="The date recorded in the Senate Executive Journal when a "
                  "federal judge was nominated for their position or the date "
                  "a state judge nominated by the legislature. When a "
                  "nomination is by primary election, this is the date of the "
                  "election. When a nomination is from a merit commission, "
                  "this is the date the nomination was announced.",
        null=True,
        blank=True,
        db_index=True,
    )
    date_elected = models.DateField(
        help_text="Judges are elected in most states. This is the date of their"
                  "first election. This field will be null if the judge was "
                  "initially selected by nomination.",
        null=True,
        blank=True,
        db_index=True,
    )
    date_recess_appointment = models.DateField(
        help_text="If a judge was appointed while congress was in recess, this "
                  "is the date of that appointment.",
        null=True,
        blank=True,
        db_index=True,
    )
    date_referred_to_judicial_committee = models.DateField(
        help_text="Federal judges are usually referred to the Judicial "
                  "Committee before being nominated. This is the date of that "
                  "referral.",
        null=True,
        blank=True,
        db_index=True,
    )
    date_judicial_committee_action = models.DateField(
        help_text="The date that the Judicial Committee took action on the "
                  "referral.",
        null=True,
        blank=True,
        db_index=True,
    )
    date_hearing = models.DateField(
        help_text="After being nominated, a judge is usually subject to a "
                  "hearing. This is the date of that hearing.",
        null=True,
        blank=True,
        db_index=True,
    )
    date_confirmation = models.DateField(
        help_text="After the hearing the senate will vote on judges. This is "
                  "the date of that vote.",
        null=True,
        blank=True,
        db_index=True,
    )
    date_start = models.DateField(
        help_text="The date the position starts active duty.",
        db_index=True,
    )
    date_granularity_start = models.CharField(
        choices=DATE_GRANULARITIES,
        max_length=15,
    )
    date_retirement = models.DateField(
        null=True,
        blank=True,
        db_index=True,
    )
    date_termination = models.DateField(
        null=True,
        blank=True,
        db_index=True,
    )
    date_granularity_termination = models.CharField(
        choices=DATE_GRANULARITIES,
        max_length=15,
        blank=True,
    )
    judicial_committee_action = models.CharField(
        choices=JUDICIAL_COMMITTEE_ACTIONS,
        max_length=20,
        blank=True,
    )
    nomination_process = models.CharField(
        choices=NOMINATION_PROCESSES,
        max_length=20,
        blank=True,
    )
    voice_vote = models.NullBooleanField(
        blank=True,
    )
    votes_yes = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
    )
    votes_no = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
    )
    how_selected = models.CharField(
        choices=SELECTION_METHODS,
        max_length=20,
        blank=True,
    )
    termination_reason = models.CharField(
        choices=TERMINATION_REASONS,
        max_length=25,
        blank=True,
    )

    def __unicode__(self):
        return u'%s: %s at %s' % (self.pk, self.person.name_full, self.court_id)

    def save(self, *args, **kwargs):
        self.full_clean()
        super(Position, self).save(*args, **kwargs)

    def clean_fields(self, *args, **kwargs):
        # Note that this isn't run during updates, alas.
        if any([self.votes_yes, self.votes_no]) and not \
                all([self.votes_yes, self.votes_no]):
            return ValidationError("votes_yes and votes_no must both be either "
                                   "empty or completed.")

        for field in ['start', 'termination']:
            validate_partial_date(self, field)

        super(Position, self).clean_fields(*args, **kwargs)


class RetentionEvent(models.Model):
    RETENTION_TYPES = (
        ('reapp_gov', 'Governor Reappointment'),
        ('reapp_leg', 'Legislative Reappointment'),
        ('elec_p', 'Partisan Election'),
        ('elec_n', 'Nonpartisan Election'),
        ('elec_u', 'Uncontested Election'),
    )
    position = models.ForeignKey(
        Position,
        related_name='retention_events',
        blank=True,
        null=True,
    )
    date_created = models.DateTimeField(
        help_text="The original creation date for the item",
        auto_now_add=True,
        db_index=True
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified.",
        auto_now=True,
        db_index=True,
    )
    retention_type = models.CharField(
        choices=RETENTION_TYPES,
        max_length=10,
    )
    date_retention = models.DateField(
        db_index=True,
    )
    votes_yes = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
    )
    votes_no = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
    )
    unopposed = models.NullBooleanField(
        null=True,
        blank=True,
    )
    won = models.NullBooleanField(
        null=True,
        blank=True,
    )


class Education(models.Model):
    DEGREE_LEVELS = (
        ('ba', "Bachelor's (e.g. B.A.)"),
        ('ma', "Master's (e.g. M.A.)"),
        ('jd', 'Juris Doctor (J.D.)'),
        ('llm', 'Master of Laws (LL.M)'),
        ('llb', 'Bachelor of Laws (e.g. LL.B)'),
        ('jsd', 'Doctor of Law (J.S.D)'),
        ('phd', 'Doctor of Philosophy (PhD)'),
        ('aa', 'Associate (e.g. A.A.)'),
        ('md', 'Medical Degree (M.D.)'),
        ('mba', 'Master of Business Administration (M.B.A.)')
    )
    date_created = models.DateTimeField(
        help_text="The original creation date for the item",
        auto_now_add=True,
        db_index=True
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified.",
        auto_now=True,
        db_index=True,
    )
    person = models.ForeignKey(
        Person,
        related_name='educations',
        blank=True,
        null=True,
    )
    school = models.ForeignKey(
        School,
        related_name='educations',
    )
    degree_level = models.CharField(
        choices=DEGREE_LEVELS,
        max_length=2,
        blank=True,
    )
    degree = models.CharField(
        max_length=100,
        blank=True,
    )
    degree_year = models.PositiveSmallIntegerField(
        help_text="The year the degree was awarded.",
        null=True,
        blank=True,
    )

    def __unicode__(self):
        return u'%s: Degree in %s from %s in the year %s' % (
            self.pk, self.degree, self.school.name, self.degree_year
        )


class Race(models.Model):
    RACES = (
        ('w', 'White'),
        ('b', 'Black or African American'),
        ('i', 'American Indian or Alaska Native'),
        ('a', 'Asian'),
        ('p', 'Native Hawaiian or Other Pacific Islander'),
        ('h', 'Hispanic/Latino'),
    )
    race = models.CharField(
        choices=RACES,
        max_length=5,
    )

    def __unicode__(self):
        # This is used in the API via the StringRelatedField. Do not cthange.
        return u"{race}".format(race=self.race)


class PoliticalAffiliation(models.Model):
    POLITICAL_AFFILIATION_SOURCE = (
        ('b', 'Ballot'),
        ('a', 'Appointer'),
        ('o', 'Other'),
    )
    POLITICAL_PARTIES = (
        ('d', 'Democrat'),
        ('r', 'Republican'),
        ('i', 'Independent'),
        ('g', 'Green'),
        ('l', 'Libertarian'),
        ('f', 'Federalist'),
        ('w', 'Whig'),
        ('j', 'Jeffersonian Republican')
    )
    date_created = models.DateTimeField(
        help_text="The original creation date for the item",
        auto_now_add=True,
        db_index=True
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified.",
        auto_now=True,
        db_index=True,
    )
    person = models.ForeignKey(
        Person,
        related_name='political_affiliations',
        blank=True,
        null=True,
    )
    political_party = models.CharField(
        choices=POLITICAL_PARTIES,
        max_length=5,
    )
    source = models.CharField(
        choices=POLITICAL_AFFILIATION_SOURCE,
        max_length=5,
        blank=True,
    )
    date_start = models.DateField(
        null=True,
        blank=True,
    )
    date_granularity_start = models.CharField(
        choices=DATE_GRANULARITIES,
        max_length=15,
        blank=True,
    )
    date_end = models.DateField(
        null=True,
        blank=True,
    )
    date_granularity_end = models.CharField(
        choices=DATE_GRANULARITIES,
        max_length=15,
        blank=True,
    )

    def clean_fields(self, *args, **kwargs):
        for field in ['start', 'end']:
            validate_partial_date(self, field)
        super(PoliticalAffiliation, self).clean_fields(*args, **kwargs)


class Source(models.Model):
    person = models.ForeignKey(
        Person,
        related_name='sources',
        blank=True,
        null=True,
    )
    date_created = models.DateTimeField(
        help_text="The original creation date for the item",
        auto_now_add=True,
        db_index=True
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified",
        auto_now=True,
        db_index=True,
    )
    url = models.URLField(
        help_text="The URL where this data was gathered.",
        max_length=2000,
        blank=True,
    )
    date_accessed = models.DateField(
        help_text="The date the data was gathered.",
        blank=True,
        null=True,
    )
    notes = models.TextField(
        help_text="Any additional notes about the data's provenance, in "
                  "Markdown format.",
        blank=True,
    )


class ABARating(models.Model):
    ABA_RATINGS = (
        ('ewq', 'Exceptionally Well Qualified'),
        ('wq', 'Well Qualified'),
        ('q', 'Qualified'),
        ('nq', 'Not Qualified'),
        ('nqa', 'Not Qualified By Reason of Age'),
    )
    person = models.ForeignKey(
        Person,
        related_name='aba_ratings',
        blank=True,
        null=True,
    )
    date_created = models.DateTimeField(
        help_text="The original creation date for the item",
        auto_now_add=True,
        db_index=True
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified.",
        auto_now=True,
        db_index=True,
    )
    date_rated = models.DateField(
        null=True,
        blank=True,
    )
    date_granularity_rated = models.CharField(
        choices=DATE_GRANULARITIES,
        max_length=15,
        blank=True,
    )
    rating = models.CharField(
        choices=ABA_RATINGS,
        max_length=5,
    )

    def clean_fields(self, *args, **kwargs):
        validate_partial_date(self, 'rated')
        super(ABARating, self).clean_fields(*args, **kwargs)
