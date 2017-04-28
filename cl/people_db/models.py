# coding=utf-8
from datetime import datetime, time

from django.core.urlresolvers import reverse
from django.db import models
from django.template import loader
from django.utils.text import slugify
from localflavor.us import models as local_models

from cl.custom_filters.templatetags.extras import granular_date
from cl.lib.model_helpers import (
    make_choices_group_lookup,
    validate_has_full_name,
    validate_is_not_alias,
    validate_partial_date,
    validate_nomination_fields_ok,
    validate_all_or_none,
    validate_exactly_n,
    validate_not_all,
    validate_at_most_n,
    validate_supervisor,
)
from cl.lib.search_index_utils import solr_list, null_map, normalize_search_dicts
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
    RELIGIONS = (
        ('ca', 'Catholic'),
        ('pr', 'Protestant'),
        ('je', 'Jewish'),
        ('mu', 'Muslim'),
        ('at', 'Atheist'),
        ('ag', 'Agnostic'),
        ('mo', 'Mormon'),
        ('bu', 'Buddhist'),
        ('hi', 'Hindu')
    )
    race = models.ManyToManyField(
        'Race',
        help_text="A person's race or races if they are multi-racial.",
        blank=True,
    )
    is_alias_of = models.ForeignKey(
        'self',
        help_text="Any nicknames or other aliases that a person has. For "
                  "example, William Jefferson Clinton has an alias to Bill",
        related_name="aliases",
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
    cl_id = models.CharField(
        max_length=30,
        help_text="A unique identifier for judge, also indicating source of "
                  "data.",
        unique=True,
        db_index=True
    )
    slug = models.SlugField(
        help_text="A generated path for this item as used in CourtListener "
                  "URLs",
        max_length=158  # len(self.name_full)
    )
    name_first = models.CharField(
        help_text="The first name of this person.",
        max_length=50,
    )
    name_middle = models.CharField(
        help_text="The middle name or names of this person",
        max_length=50,
        blank=True,
    )
    name_last = models.CharField(
        help_text="The last name of this person",
        max_length=50,
        db_index=True,
    )
    name_suffix = models.CharField(
        help_text="Any suffixes that this person's name may have",
        choices=SUFFIXES,
        max_length=5,
        blank=True,
    )
    date_dob = models.DateField(
        help_text="The date of birth for the person",
        null=True,
        blank=True,
    )
    date_granularity_dob = models.CharField(
        choices=DATE_GRANULARITIES,
        max_length=15,
        blank=True,
    )
    date_dod = models.DateField(
        help_text="The date of death for the person",
        null=True,
        blank=True,
    )
    date_granularity_dod = models.CharField(
        choices=DATE_GRANULARITIES,
        max_length=15,
        blank=True,
    )
    dob_city = models.CharField(
        help_text="The city where the person was born.",
        max_length=50,
        blank=True,
    )
    dob_state = local_models.USStateField(
        help_text="The state where the person was born.",
        blank=True,
    )
    dod_city = models.CharField(
        help_text="The city where the person died.",
        max_length=50,
        blank=True,
    )
    dod_state = local_models.USStateField(
        help_text="The state where the person died.",
        blank=True,
    )
    gender = models.CharField(
        help_text="The person's gender",
        choices=GENDERS,
        max_length=2,
        blank=True,
    )
    religion = models.CharField(
        help_text="The religion of a person",
        max_length=30,
        blank=True
    )
    ftm_total_received = models.FloatField(
        help_text="The amount of money received by this person and logged by "
                  "Follow the Money.",
        blank=True,
        null=True,
        db_index=True,
    )
    ftm_eid = models.CharField(
        max_length=30,
        help_text="The ID of a judge as assigned by the Follow the Money "
                  "database.",
        null=True,
        blank=True,
    )
    has_photo = models.BooleanField(
        help_text="Whether there is a photo corresponding to this person in "
                  "the judge pics project.",
        default=False,
    )

    def __unicode__(self):
        return u'%s: %s' % (self.pk, self.name_full)

    class Meta:
        verbose_name_plural = "people"

    def get_absolute_url(self):
        return reverse('view_person', args=[self.pk, self.slug])

    def save(self, *args, **kwargs):
        self.slug = slugify(trunc(self.name_full, 158))
        self.full_clean()
        super(Person, self).save(*args, **kwargs)

    def clean_fields(self, *args, **kwargs):
        validate_partial_date(self, ['dob', 'dod'])
        validate_is_not_alias(self, ['is_alias_of'])
        validate_has_full_name(self)
        super(Person, self).clean_fields(*args, **kwargs)

    @property
    def name_full(self):
        return u' '.join([v for v in [
            self.name_first,
            self.name_middle,
            self.name_last,
            self.get_name_suffix_display(),
        ] if v]).strip()

    @property
    def name_full_reverse(self):
        return u'{name_last}, {name_first} {name_middle}, {suffix}'.format(
            suffix=self.get_name_suffix_display(),
            **self.__dict__
        ).strip(', ')

    @property
    def is_alias(self):
        return True if self.is_alias_of is not None else False

    @property
    def is_judge(self):
        """Examine the positions a person has had and identify if they were ever
        a judge.
        """
        for position in self.positions.all():
            if position.is_judicial_position:
                return True
        return False

    def as_search_dict(self):
        """Create a dict that can be ingested by Solr"""
        out = {
            'id': self.pk,
            'fjc_id': self.fjc_id,
            'cl_id': self.cl_id,
            'alias_ids': [alias.pk for alias in self.aliases.all()],
            'races': [r.get_race_display() for r in self.race.all()],
            'gender': self.get_gender_display(),
            'religion': self.religion,
            'name': self.name_full,
            'name_reverse': self.name_full_reverse,
            'date_granularity_dob': self.date_granularity_dob,
            'date_granularity_dod': self.date_granularity_dod,
            'dob_city': self.dob_city,
            'dob_state': self.get_dob_state_display(),
            'dob_state_id': self.dob_state,
            'absolute_url': self.get_absolute_url(),
            'school': [e.school.name for e in self.educations.all()],
            'political_affiliation': [
                pa.get_political_party_display() for pa in
                self.political_affiliations.all() if pa
            ],
            'political_affiliation_id': [
                pa.political_party for pa in
                self.political_affiliations.all() if pa
            ],
            'aba_rating': [
                r.get_rating_display() for r in
                self.aba_ratings.all() if r
            ],
        }

        # Dates
        if self.date_dob is not None:
            out['dob'] = datetime.combine(self.date_dob, time())
        if self.date_dod is not None:
            out['dod'] = datetime.combine(self.date_dod, time())

        # Joined Values. Brace yourself.
        positions = self.positions.all()
        if positions.count() > 0:
            p_out = {
                'court': [p.court.short_name for p in positions if p.court],
                'court_exact': [p.court.pk for p in positions if p.court],
                'position_type': [p.get_position_type_display() for p in
                                  positions],
                'appointer': [p.appointer.person.name_full_reverse for p in
                              positions if p.appointer],
                'supervisor': [p.supervisor.name_full_reverse for p in
                               positions if p.supervisor],
                'predecessor': [p.predecessor.name_full_reverse for p in
                                positions if p.predecessor],
                'date_nominated': solr_list(positions, 'date_nominated'),
                'date_elected': solr_list(positions, 'date_elected'),
                'date_recess_appointment': solr_list(
                    positions, 'date_recess_appointment',
                ),
                'date_referred_to_judicial_committee': solr_list(
                    positions, 'date_referred_to_judicial_committee',
                ),
                'date_judicial_committee_action': solr_list(
                    positions, 'date_judicial_committee_action',
                ),
                'date_hearing': solr_list(positions, 'date_hearing'),
                'date_confirmation': solr_list(positions, 'date_confirmation'),
                'date_start': solr_list(positions, 'date_start'),
                'date_granularity_start': solr_list(
                    positions, 'date_granularity_start',
                ),
                'date_retirement': solr_list(
                    positions, 'date_retirement',
                ),
                'date_termination': solr_list(
                    positions, 'date_termination',
                ),
                'date_granularity_termination': solr_list(
                    positions, 'date_granularity_termination',
                ),
                'judicial_committee_action': [
                    p.get_judicial_committee_action_display() for p in
                    positions if p.judicial_committee_action
                ],
                'nomination_process': [
                    p.get_nomination_process_display() for p in
                    positions if p.nomination_process
                ],
                'selection_method': [
                    p.get_how_selected_display() for p in
                    positions if p.how_selected
                ],
                'selection_method_id': [
                    p.how_selected for p in
                    positions if p.how_selected
                ],
                'termination_reason': [
                    p.get_termination_reason_display() for p in
                    positions if p.termination_reason
                ],
            }
            out.update(p_out)

        text_template = loader.get_template('indexes/person_text.txt')
        out['text'] = text_template.render({'item': self}).translate(null_map)

        return normalize_search_dicts(out)


class School(models.Model):
    is_alias_of = models.ForeignKey(
        'self',
        help_text="Any alternate names that a school may have",
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
        help_text="The name of the school or alias",
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

    @property
    def is_alias(self):
        return True if self.is_alias_of is not None else False

    def save(self, *args, **kwargs):
        self.full_clean()
        super(School, self).save(*args, **kwargs)

    def clean_fields(self, *args, **kwargs):
        # An alias cannot be an alias.
        validate_is_not_alias(self, ['is_alias_of'])
        super(School, self).clean_fields(*args, **kwargs)


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
            ('c-mag',     'Chief Magistrate'),
            ('c-spec-m',  'Chief Special Master'),
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
            ('pres',          'President of the United States'),
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
    POSITION_TYPE_GROUPS = make_choices_group_lookup(POSITION_TYPES)
    NOMINATION_PROCESSES = (
        ('fed_senate', 'U.S. Senate'),
        ('state_senate', 'State Senate'),
        ('election', 'Primary Election'),
        ('merit_comm', 'Merit Commission'),
    )
    VOTE_TYPES = (
        ('s', 'Senate'),
        ('p', 'Partisan Election'),
        ('np', 'Non-Partisan Election'),
    )
    JUDICIAL_COMMITTEE_ACTIONS = (
        ('no_rep', 'Not Reported'),
        ('rep_w_rec', 'Reported with Recommendation'),
        ('rep_wo_rec', 'Reported without Recommendation'),
        ('rec_postpone', 'Recommendation Postponed'),
        ('rec_bad', 'Recommended Unfavorably'),
    )
    SELECTION_METHODS = (
        ('Election', (
            ('e_part', 'Partisan Election'),
            ('e_non_part', 'Non-Partisan Election'),

        )),
        ('Appointment', (
            ('a_pres', 'Appointment (President)'),
            ('a_gov', 'Appointment (Governor)'),
            ('a_legis', 'Appointment (Legislature)'),
        )),
    )
    SELECTION_METHOD_GROUPS = make_choices_group_lookup(SELECTION_METHODS)
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
        help_text="If this is a judicial position, this indicates the role the "
                  "person had. This field may be blank if job_title is "
                  "complete instead.",
        choices=POSITION_TYPES,
        max_length=20,
        blank=True,
        null=True,
    )
    job_title = models.CharField(
        help_text="If title isn't in position_type, a free-text position may "
                  "be entered here.",
        max_length=100,
        blank=True,
    )
    person = models.ForeignKey(
        Person,
        help_text="The person that held the position.",
        related_name='positions',
        blank=True,
        null=True,
    )
    court = models.ForeignKey(
        Court,
        help_text="If this was a judicial position, this is the jurisdiction "
                  "where it was held.",
        related_name='court_positions',
        blank=True,
        null=True,
    )
    school = models.ForeignKey(
        School,
        help_text="If this was an academic job, this is the school where the "
                  "person worked.",
        blank=True,
        null=True,
    )
    organization_name = models.CharField(
        help_text="If the organization where this position was held is not a "
                  "school or court, this is the place it was held.",
        max_length=120,
        blank=True,
        null=True,
    )
    location_city = models.CharField(
        help_text="If not a court or school, the city where person worked.",
        max_length=50,
        blank=True,
    )
    location_state = local_models.USStateField(
        help_text="If not a court or school, the state where person worked.",
        blank=True,
    )
    appointer = models.ForeignKey(
        'self',
        help_text="If this is an appointed position, the person-position "
                  "responsible for the appointment. This field references "
                  "other positions instead of referencing people because that "
                  "allows you to know the position a person held when an "
                  "appointment was made.",
        related_name='appointed_positions',
        blank=True,
        null=True,
    )
    supervisor = models.ForeignKey(
        Person,
        help_text="If this is a clerkship, the supervising judge.",
        related_name='supervised_positions',
        blank=True,
        null=True,
    )
    predecessor = models.ForeignKey(
        Person,
        help_text="The person that previously held this position",
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
    judicial_committee_action = models.CharField(
        help_text="The action that the judicial committee took in response to "
                  "a nomination",
        choices=JUDICIAL_COMMITTEE_ACTIONS,
        max_length=20,
        blank=True,
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
    date_termination = models.DateField(
        help_text="The last date of their employment. The compliment to "
                  "date_start",
        null=True,
        blank=True,
        db_index=True,
    )
    termination_reason = models.CharField(
        help_text="The reason for a termination",
        choices=TERMINATION_REASONS,
        max_length=25,
        blank=True,
    )
    date_granularity_termination = models.CharField(
        choices=DATE_GRANULARITIES,
        max_length=15,
        blank=True,
    )
    date_retirement = models.DateField(
        help_text="The date when they become a senior judge by going into "
                  "active retirement",
        null=True,
        blank=True,
        db_index=True,
    )
    nomination_process = models.CharField(
        help_text="The process by which a person was nominated into this "
                  "position.",
        choices=NOMINATION_PROCESSES,
        max_length=20,
        blank=True,
    )
    vote_type = models.CharField(
        help_text="The type of vote that resulted in this position.",
        choices=VOTE_TYPES,
        max_length=2,
        blank=True,
    )
    voice_vote = models.NullBooleanField(
        help_text="Whether the Senate voted by voice vote for this position.",
        blank=True,
    )
    votes_yes = models.PositiveIntegerField(
        help_text="If votes are an integer, this is the number of votes in "
                  "favor of a position.",
        null=True,
        blank=True,
    )
    votes_no = models.PositiveIntegerField(
        help_text="If votes are an integer, this is the number of votes "
                  "opposed to a position.",
        null=True,
        blank=True,
    )
    votes_yes_percent = models.FloatField(
        help_text="If votes are a percentage, this is the percentage of votes "
                  "in favor of a position.",
        null=True,
        blank=True,
    )
    votes_no_percent = models.FloatField(
        help_text="If votes are a percentage, this is the percentage of votes "
                  "opposed to a position.",
        null=True,
        blank=True,
    )
    how_selected = models.CharField(
        help_text="The method that was used for selecting this judge for this "
                  "position (generally an election or appointment).",
        choices=SELECTION_METHODS,
        max_length=20,
        blank=True,
    )
    has_inferred_values = models.BooleanField(
        help_text="Some or all of the values for this position were inferred "
                  "from a data source instead of manually added. See sources "
                  "field for more details.",
        default=False,
    )

    def __unicode__(self):
        return u'%s: %s at %s' % (self.pk, self.person.name_full, self.court_id)

    @property
    def is_judicial_position(self):
        """Return True if the position is judicial."""
        if self.POSITION_TYPE_GROUPS.get(self.position_type) == 'Judge':
            return True
        return False

    @property
    def is_clerkship(self):
        """Return True if the position is a clerkship."""
        if self.POSITION_TYPE_GROUPS.get(self.position_type) == 'Clerkships':
            return True
        return False

    @property
    def vote_string(self):
        """Make a human-friendly string from the vote information"""
        s = ''

        # Do vote type first
        if self.vote_type == 's':
            s += "Senate voted"
            if self.voice_vote:
                s += ' <span class="alt">by</span> voice vote'
        elif self.vote_type in ['p', 'np']:
            s += self.get_vote_type_display()

        # Then do vote counts/percentages, if we have that info.
        if self.votes_yes or self.votes_yes_percent:
            s += ', '
        if self.votes_yes:
            s += '%s in favor <span class="alt">and</span> %s ' \
                           'opposed' % (self.votes_yes, self.votes_no)
        elif self.votes_yes_percent:
            s += '%g%% in favor <span class="alt">and</span> ' \
                           '%g%% opposed' % (self.votes_yes_percent,
                                             self.votes_no_percent)
        return s

    @property
    def html_title(self):
        """Display the position as a title."""
        s = ''

        # Title
        if self.get_position_type_display():
            s += self.get_position_type_display()
        else:
            s += self.job_title

        # Where
        if self.school or self.organization_name or self.court:
            s += ' <span class="alt text-lowercase">at</span> '
            if self.court:
                s += self.court.full_name
            elif self.school:
                s += self.school
            elif self.organization_name:
                s += self.organization_name

        # When
        if self.date_start or self.date_termination:
            if self.date_termination:
                end_date = granular_date(self, 'date_termination')
            else:
                # If we don't know when the position ended, we use a ? if the
                # person has died, or say Present if they're alive.
                if self.person.date_dod:
                    end_date = "?"
                else:
                    end_date = "Present"

            s += ' <span class="text-capitalize">(%s &ndash; %s)' % (
                granular_date(self, 'date_start', default="Unknown Date"),
                end_date,
            )
        return s

    @property
    def sorted_appointed_positions(self):
        """Appointed positions, except sorted by date instead of name."""
        return self.appointed_positions.all().order_by('-date_start')

    def save(self, *args, **kwargs):
        self.full_clean()
        super(Position, self).save(*args, **kwargs)

    def clean_fields(self, *args, **kwargs):
        validate_partial_date(self, ['start', 'termination'])
        validate_is_not_alias(self, ['person', 'supervisor', 'predecessor',
                                     'school'])
        validate_at_most_n(self, 1, ['school', 'organization_name', 'court'])
        validate_exactly_n(self, 1, ['position_type', 'job_title'])
        validate_all_or_none(self, ['votes_yes', 'votes_no'])
        validate_all_or_none(self, ['votes_yes_percent', 'votes_no_percent'])
        validate_not_all(self, ['votes_yes', 'votes_no', 'votes_yes_percent',
                                'votes_no_percent'])
        validate_nomination_fields_ok(self)
        validate_supervisor(self)

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
        help_text="The position that was retained by this event.",
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
        help_text="The method through which this position was retained.",
        choices=RETENTION_TYPES,
        max_length=10,
    )
    date_retention = models.DateField(
        help_text="The date of retention",
        db_index=True,
    )
    votes_yes = models.PositiveIntegerField(
        help_text="If votes are an integer, this is the number of votes in "
                  "favor of a position.",
        null=True,
        blank=True,
    )
    votes_no = models.PositiveIntegerField(
        help_text="If votes are an integer, this is the number of votes "
                  "opposed to a position.",
        null=True,
        blank=True,
    )
    votes_yes_percent = models.FloatField(
        help_text="If votes are a percentage, this is the percentage of votes "
                  "in favor of a position.",
        null=True,
        blank=True,
    )
    votes_no_percent = models.FloatField(
        help_text="If votes are a percentage, this is the percentage of votes "
                  "opposed to a position.",
        null=True,
        blank=True,
    )
    unopposed = models.NullBooleanField(
        help_text="Whether the position was unopposed at the time of "
                  "retention.",
        null=True,
        blank=True,
    )
    won = models.NullBooleanField(
        help_text="Whether the retention event was won.",
        null=True,
        blank=True,
    )

    def save(self, *args, **kwargs):
        self.full_clean()
        super(RetentionEvent, self).save(*args, **kwargs)

    def clean_fields(self, *args, **kwargs):
        validate_all_or_none(self, ['votes_yes', 'votes_no'])
        validate_all_or_none(self, ['votes_yes_percent', 'votes_no_percent'])
        super(RetentionEvent, self).clean_fields(*args, **kwargs)


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
        ('mba', 'Master of Business Administration (M.B.A.)'),
        ('cfa', 'Accounting Certification (C.P.A., C.M.A., C.F.A.)'),
        ('cert', 'Certificate')
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
        help_text="The person that completed this education",
        related_name='educations',
        blank=True,
        null=True,
    )
    school = models.ForeignKey(
        School,
        help_text="The school where this education was compeleted",
        related_name='educations',
    )
    degree_level = models.CharField(
        help_text="Normalized degree level, e.g. BA, JD.",
        choices=DEGREE_LEVELS,
        max_length=4,
        blank=True,
    )
    degree_detail = models.CharField(
        help_text="Detailed degree description, e.g. including major.",
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
            self.pk, self.degree_detail, self.school.name, self.degree_year
        )

    def save(self, *args, **kwargs):
        self.full_clean()
        super(Education, self).save(*args, **kwargs)

    def clean_fields(self, *args, **kwargs):
        # Note that this isn't run during updates, alas.
        validate_is_not_alias(self, ['person', 'school'])
        super(Education, self).clean_fields(*args, **kwargs)


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
        unique=True,
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
        ('j', 'Jeffersonian Republican'),
        ('u', 'National Union'),
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
        help_text="The person with the political affiliation",
        related_name='political_affiliations',
        blank=True,
        null=True,
    )
    political_party = models.CharField(
        help_text="The political party the person is affiliated with.",
        choices=POLITICAL_PARTIES,
        max_length=5,
    )
    source = models.CharField(
        help_text="The source of the political affiliation -- where it is "
                  "documented that this affiliation exists.",
        choices=POLITICAL_AFFILIATION_SOURCE,
        max_length=5,
        blank=True,
    )
    date_start = models.DateField(
        help_text="The date the political affiliation was first documented",
        null=True,
        blank=True,
    )
    date_granularity_start = models.CharField(
        choices=DATE_GRANULARITIES,
        max_length=15,
        blank=True,
    )
    date_end = models.DateField(
        help_text="The date the affiliation ended.",
        null=True,
        blank=True,
    )
    date_granularity_end = models.CharField(
        choices=DATE_GRANULARITIES,
        max_length=15,
        blank=True,
    )

    def save(self, *args, **kwargs):
        self.full_clean()
        super(PoliticalAffiliation, self).save(*args, **kwargs)

    def clean_fields(self, *args, **kwargs):
        validate_partial_date(self, ['start', 'end'])
        validate_is_not_alias(self, ['person'])
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
        help_text="The person rated by the American Bar Association",
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
    year_rated = models.PositiveSmallIntegerField(
        help_text="The year of the rating.",
        null=True
    )
    rating = models.CharField(
        help_text="The rating given to the person.",
        choices=ABA_RATINGS,
        max_length=5,
    )

    class Meta:
        verbose_name = 'American Bar Association Rating'
        verbose_name_plural = 'American Bar Association Ratings'

    def save(self, *args, **kwargs):
        self.full_clean()
        super(ABARating, self).save(*args, **kwargs)

    def clean_fields(self, *args, **kwargs):
        validate_is_not_alias(self, ['person'])
        super(ABARating, self).clean_fields(*args, **kwargs)


class PartyType(models.Model):
    docket = models.ForeignKey(
        'search.Docket',
        related_name="party_types",
    )
    party = models.ForeignKey(
        'Party',
        related_name="party_types",
    )
    name = models.CharField(
        help_text="The name of the type (Defendant, Plaintiff, etc.)",
        max_length="100",  # 2× the max in first 100,000 sampled.
        db_index=True,
    )

    class Meta:
        unique_together = ('docket', 'party', 'name')

    def __unicode__(self):
        return u'%s: Party %s is %s in Docket %s' % (
            self.pk,
            self.party_id,
            self.name,
            self.docket_id,
        )


class Party(models.Model):
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
    attorneys = models.ManyToManyField(
        'Attorney',
        help_text="The attorneys involved with the party.",
        through="Role",
        related_name="parties",
    )
    name = models.TextField(
        help_text="The name of the party.",
        db_index=True,
    )
    extra_info = models.TextField(
        help_text="Additional info from PACER",
        db_index=True,
    )

    class Meta:
        unique_together = ('name', 'extra_info')
        verbose_name_plural = "Parties"
        permissions = (
            ("has_recap_api_access", "Can work with RECAP API"),
        )

    def __unicode__(self):
        return u'%s: %s' % (self.pk, self.name)


class Role(models.Model):
    ATTORNEY_TO_BE_NOTICED = 1
    ATTORNEY_LEAD = 2
    ATTORNEY_IN_SEALED_GROUP = 3
    PRO_HAC_VICE = 4
    SELF_TERMINATED = 5
    TERMINATED = 6
    SUSPENDED = 7
    INACTIVE = 8
    DISBARRED = 9
    UNKNOWN = 10
    ATTORNEY_ROLES = (
        (ATTORNEY_TO_BE_NOTICED, "Attorney to be noticed"),
        (ATTORNEY_LEAD, "Lead attorney"),
        (ATTORNEY_IN_SEALED_GROUP, "Attorney in sealed group"),
        (PRO_HAC_VICE, "Pro hac vice"),
        (SELF_TERMINATED, "Self-terminated"),
        (TERMINATED, "Terminated"),
        (SUSPENDED, "Suspended"),
        (INACTIVE, "Inactive"),
        (DISBARRED, "Disbarred"),
        (UNKNOWN, "Unknown"),
    )
    party = models.ForeignKey(
        Party,
        related_name="roles",
    )
    attorney = models.ForeignKey(
        "Attorney",
        related_name="roles",
    )
    docket = models.ForeignKey(
        "search.Docket",
        help_text="The attorney represented the party on this docket in this "
                  "role.",
    )
    role = models.SmallIntegerField(
        help_text="The name of the attorney's role.",
        choices=ATTORNEY_ROLES,
        db_index=True,
    )
    date_action = models.DateField(
        help_text="The date the attorney was disbarred, suspended, "
                  "terminated...",
        null=True,
    )

    class Meta:
        unique_together = ('party', 'attorney', 'role', 'docket', 'date_action')

    def __unicode__(self):
        return u'%s: Attorney %s is %s for Party %s' % (
            self.pk,
            self.attorney_id,
            self.get_role_display(),
            self.party_id,
        )


class Attorney(models.Model):
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
    date_sourced = models.DateField(
        help_text="The latest date on the source docket that populated this "
                  "information. When information is in conflict use the "
                  "latest data.",
        db_index=True,
    )
    organizations = models.ManyToManyField(
        'AttorneyOrganization',
        help_text="The organizations that the attorney is affiliated with",
        related_name="attorneys",
        through="AttorneyOrganizationAssociation",
    )
    name = models.TextField(
        help_text="The name of the attorney.",
        db_index=True,
    )
    contact_raw = models.TextField(
        help_text="The raw contents of the contact field",
        db_index=True,
    )
    phone = local_models.PhoneNumberField(
        help_text="The phone number of the attorney.",
    )
    fax = local_models.PhoneNumberField(
        help_text="The fax number of the attorney.",
    )
    email = models.EmailField(
        help_text="The email address of the attorney.",
    )

    class Meta:
        unique_together = ('name', 'contact_raw')
        permissions = (
            ("has_recap_api_access", "Can work with RECAP API"),
        )

    def __unicode__(self):
        return u'%s: %s' % (self.pk, self.name)


class AttorneyOrganizationAssociation(models.Model):
    """A through table linking an attorneys with organizations.

    E.g: "This attorney worked at this organization on this case."

    This way, we when we know that an attorney worked at four different firms,
    we also know what they did while there.
    """
    attorney = models.ForeignKey(
        Attorney,
        related_name="attorney_organization_associations",
    )
    attorney_organization = models.ForeignKey(
        "AttorneyOrganization",
        related_name="attorney_organization_associations",
    )
    docket = models.ForeignKey(
        "search.Docket",
        help_text="The docket that the attorney worked on while at this "
                  "organization.",
    )

    class Meta:
        unique_together = ('attorney', 'attorney_organization', 'docket')

    def __unicode__(self):
        return u'%s: Atty %s worked on docket %s while at org %s' % (
            self.pk,
            self.attorney_id,
            self.docket_id,
            self.attorney_organization_id,
        )


class AttorneyOrganization(models.Model):
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
    lookup_key = models.TextField(
        help_text="A trimmed version of the address for duplicate matching.",
        db_index=True,
        unique=True,
    )
    name = models.TextField(
        help_text="The name of the organization.",
        db_index=True,
    )
    address1 = models.TextField(
        help_text="The normalized address1 of the organization",
        db_index=True,
    )
    address2 = models.TextField(
        help_text="The normalized address2 of the organization",
        db_index=True,
    )
    city = models.TextField(
        help_text="The normalized city of the organization",
        db_index=True,
    )
    state = local_models.USPostalCodeField(
        help_text="The two-letter USPS postal abbreviation for the "
                  "organization",
        db_index=True,
    )
    zip_code = local_models.USZipCodeField(
        help_text="The zip code for the organization, XXXXX or XXXXX-XXXX "
                  "work.",
        db_index=True,
    )

    class Meta:
        unique_together = ('name', 'address1', 'address2', 'city', 'state',
                           'zip_code')

    def __unicode__(self):
        return "%s: %s, %s, %s, %s, %s, %s" % (
            self.pk,
            self.name,
            self.address1,
            self.address2,
            self.city,
            self.state,
            self.zip_code,
        )
