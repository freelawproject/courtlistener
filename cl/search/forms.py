import re

from django import forms
from django.forms import DateField
from localflavor.us.us_states import STATE_CHOICES

from cl.people_db.models import Position, PoliticalAffiliation
from cl.search.fields import CeilingDateField
from cl.search.fields import FloorDateField
from cl.search.models import Court
from cl.search.models import DOCUMENT_STATUSES


OPINION_ORDER_BY_CHOICES = (
    ('score desc',       'Relevance'),
    ('dateFiled desc',   'Newest First'),
    ('dateFiled asc',    'Oldest First'),
    ('citeCount desc',   'Most Cited First'),
    ('citeCount asc',    'Least Cited First'),
    ('dateArgued desc',  'Newest First'),
    ('dateArgued asc',   'Oldest First'),
    ('name_reverse asc', 'Name'),
    ('dob desc,name_reverse asc', 'Most Recently Born'),
    ('dob asc,name_reverse asc',  'Least Recently Born'),
    ('dod desc,name_reverse asc', 'Most Recently Deceased'),
)

TYPE_CHOICES = (
    ('o', 'Opinions'),
    ('oa', 'Oral Arguments'),
    ('p', 'People'),
    ('r', 'RECAP'),
)


def _clean_form(request, cd):
    """Returns cleaned up values as a Form object.
    """
    # Make a copy of request.GET so it is mutable
    mutable_GET = request.GET.copy()

    # Send the user the cleaned up query
    mutable_GET['q'] = cd['q']

    # Clean up the date formats
    for date_field in SearchForm().get_date_field_names():
        for time in ('before', 'after'):
            field = "%s_%s" % (date_field, time)
            if mutable_GET.get(field) and cd.get(field) is not None:
                # Don't use strftime. It'll fail before 1900
                before = cd[field]
                mutable_GET[field] = '%s-%02d-%02d' % \
                                     (before.year, before.month, before.day)

    mutable_GET['order_by'] = cd['order_by']
    mutable_GET['type'] = cd['type']

    courts = Court.objects.filter(in_use=True).values(
        'pk', 'short_name', 'jurisdiction', 'has_oral_argument_scraper')
    for court in courts:
        mutable_GET['court_%s' % court['pk']] = cd['court_%s' % court['pk']]

    return SearchForm(mutable_GET)


class SearchForm(forms.Form):
    #
    # Blended fields
    #
    type = forms.ChoiceField(
        choices=TYPE_CHOICES,
        required=False,
        initial='o',
        widget=forms.RadioSelect(
            attrs={'class': 'external-input form-control'}
        )
    )
    q = forms.CharField(
        required=False
    )
    court = forms.CharField(
        required=False,
        widget=forms.HiddenInput()
    )
    order_by = forms.ChoiceField(
        choices=OPINION_ORDER_BY_CHOICES,
        required=False,
        label='Result Ordering',
        initial='score desc',
        widget=forms.Select(
            attrs={'class': 'external-input form-control'}
        )
    )

    #
    # Oral argument and Opinion shared fields
    #
    case_name = forms.CharField(
        required=False,
        label='Case Name',
        initial='',
        widget=forms.TextInput(
            attrs={'class': 'external-input form-control',
                   'autocomplete': 'off'}
        )
    )
    judge = forms.CharField(
        required=False,
        initial='',
        widget=forms.TextInput(
            attrs={'class': 'external-input form-control',
                   'autocomplete': 'off'}
        )
    )
    docket_number = forms.CharField(
        required=False,
        label='Docket Number',
        widget=forms.TextInput(
            attrs={'class': 'external-input form-control',
                   'autocomplete': 'off'}
        )
    )

    #
    # RECAP fields
    #
    available_only = forms.BooleanField(
        label="Only show items with archived PDFs",
        label_suffix='',
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'external-input form-control left',
        }),
    )
    description = forms.CharField(
        required=False,
        label="Document Description",
        widget=forms.TextInput(
            attrs={'class': 'external-input form-control',
                   'autocomplete': 'off'}
        )
    )
    nature_of_suit = forms.CharField(
        required=False,
        label="Nature of Suit",
        widget=forms.TextInput(
            attrs={'class': 'external-input form-control',
                   'autocomplete': 'off'}
        )
    )
    assigned_to = forms.CharField(
        required=False,
        label="Assigned To Judge",
        widget=forms.TextInput(
            attrs={'class': 'external-input form-control',
                   'autocomplete': 'off'}
        )
    )
    referred_to = forms.CharField(
        required=False,
        label="Referred To Judge",
        widget=forms.TextInput(
            attrs={'class': 'external-input form-control',
                   'autocomplete': 'off'}
        )
    )
    document_number = forms.CharField(
        required=False,
        label="Document #",
        widget=forms.TextInput(
            attrs={'class': 'external-input form-control',
                   'autocomplete': 'off'}
        )
    )
    attachment_number = forms.CharField(
        required=False,
        label="Attachment #",
        widget=forms.TextInput(
            attrs={'class': 'external-input form-control',
                   'autocomplete': 'off'}
        )
    )

    #
    # Oral argument fields
    #
    argued_after = FloorDateField(
        required=False,
        label="Argued After",
        widget=forms.TextInput(
            attrs={'placeholder': 'YYYY-MM-DD',
                   'class': 'external-input form-control',
                   'autocomplete': 'off'}
        )
    )
    argued_before = CeilingDateField(
        required=False,
        label="Argued Before",
        widget=forms.TextInput(
            attrs={'placeholder': 'YYYY-MM-DD',
                   'class': 'external-input form-control',
                   'autocomplete': 'off'}
        )
    )

    #
    # Opinion fields
    #
    filed_after = FloorDateField(
        required=False,
        label='Filed After',
        widget=forms.TextInput(
            attrs={'placeholder': 'YYYY-MM-DD',
                   'class': 'external-input form-control',
                   'autocomplete': 'off'}
        )
    )
    filed_before = CeilingDateField(
        required=False,
        label='Filed Before',
        widget=forms.TextInput(
            attrs={'placeholder': 'YYYY-MM-DD',
                   'class': 'external-input form-control',
                   'autocomplete': 'off'}
        )
    )
    citation = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={'class': 'external-input form-control',
                   'autocomplete': 'off'}
        )
    )
    neutral_cite = forms.CharField(
        required=False,
        label='Neutral Citation',
        widget=forms.TextInput(
            attrs={'class': 'external-input form-control',
                   'autocomplete': 'off'}
        )
    )
    cited_gt = forms.CharField(
        required=False,
        label='Min Cites',
        initial=0,
        widget=forms.TextInput(
            attrs={'class': 'external-input form-control',
                   'autocomplete': 'off'}
        )
    )
    cited_lt = forms.CharField(
        required=False,
        label='Max Cites',
        initial=60000,
        widget=forms.TextInput(
            attrs={'class': 'external-input form-control',
                   'autocomplete': 'off'}
        )
    )

    #
    # Judge fields
    #
    name = forms.CharField(
        required=False,
        label='Name',
        widget=forms.TextInput(
            attrs={'class': 'external-input form-control',
                   'autocomplete': 'off'}
        )
    )
    born_after = FloorDateField(
        required=False,
        label="Born After",
        widget=forms.TextInput(
            attrs={'placeholder': 'YYYY-MM-DD',
                   'class': 'external-input form-control',
                   'autocomplete': 'off'}
        )
    )
    born_before = CeilingDateField(
        required=False,
        label="Born Before",
        widget=forms.TextInput(
            attrs={'placeholder': 'YYYY-MM-DD',
                   'class': 'external-input form-control',
                   'autocomplete': 'off'}
        )
    )
    dob_city = forms.CharField(
        required=False,
        label='Birth City',
        widget=forms.TextInput(
                attrs={'class': 'external-input form-control',
                       'autocomplete': 'off'}
        )
    )
    dob_state = forms.ChoiceField(
        choices=[('', '---------')] + list(STATE_CHOICES),
        required=False,
        label='Birth State',
        widget=forms.Select(
            attrs={'class': 'external-input form-control'}
        )
    )
    school = forms.CharField(
        required=False,
        label='School Attended',
        widget=forms.TextInput(
            attrs={'class': 'external-input form-control',
                   'autocomplete': 'off'}
        )
    )
    appointer = forms.CharField(
        required=False,
        label='Appointed By',
        widget=forms.TextInput(
            attrs={'class': 'external-input form-control',
                   'autocomplete': 'off'}
        )
    )
    selection_method = forms.ChoiceField(
        choices=[('', '---------')] + list(Position.SELECTION_METHODS),
        required=False,
        label='Selection Method',
        initial='None',
        widget=forms.Select(
            attrs={'class': 'external-input form-control'}
        )
    )
    political_affiliation = forms.ChoiceField(
        choices=[('', '---------')] + list(PoliticalAffiliation.POLITICAL_PARTIES),
        required=False,
        label='Political Affiliation',
        initial='None',
        widget=forms.Select(
            attrs={'class': 'external-input form-control'}
        )
    )

    def get_date_field_names(self):
        return {f_name.split('_')[0] for f_name, f in self.fields.items()
                if isinstance(f, DateField)}

    def __init__(self, *args, **kwargs):
        super(SearchForm, self).__init__(*args, **kwargs)
        """
        Normally we wouldn't need to use __init__ in a form object like
        this, however, since we are generating checkbox fields with dynamic
        names coming from the database, we need to interact directly with the
        fields dict.
        """
        courts = Court.objects.filter(in_use=True).values(
            'pk', 'short_name', 'jurisdiction', 'has_oral_argument_scraper')
        for court in courts:
            self.fields['court_' + court['pk']] = forms.BooleanField(
                label=court['short_name'],
                required=False,
                initial=True,
                widget=forms.CheckboxInput(attrs={'checked': 'checked'})
            )

        for status in DOCUMENT_STATUSES:
            attrs = {}
            if status[1] == 'Precedential':
                initial = True
                attrs.update({'checked': 'checked'})
            else:
                initial = False
            self.fields['stat_' + status[1]] = forms.BooleanField(
                label=status[1],
                required=False,
                initial=initial,
                widget=forms.CheckboxInput(attrs=attrs)
            )

    # This is a particularly nasty area of the code due to several factors:
    #  1. Django doesn't have a good method of setting default values for
    #     bound forms. As a result, we set them here as part of a cleanup
    #     routine. This way a user can do a query for page=2, and still have
    #     all the correct defaults.
    #  2. In our search form, part of what we do is clean up the GET requests
    #     that the user sent. This is completed in clean_form(). This allows a
    #     user to be taught what better queries look like. To do this, we have
    #     to make a temporary variable in _clean_form() and assign it
    #     the values of the cleaned_data. The upshot of this is that most
    #     changes made here will also need to be made in _clean_form().
    #     Failure to do that will result in the query being processed correctly
    #     (search results are all good), but the form on the UI won't be
    #     cleaned up for the user, making things rather confusing.
    #  3. We do some cleanup work in search_utils.make_stats_variable(). The
    #     work that's done there is used to check or un-check the boxes in the
    #     sidebar, so if you tweak how they work you'll need to tweak this
    #     function.
    # In short: This is a nasty area. Comments this long are a bad sign for
    # the intrepid developer.
    def clean_q(self):
        """
        Cleans up various problems with the query:
         - lowercase --> camelCase
         - '|' --> ' OR '
        """
        q = self.cleaned_data['q']

        # Fix fields to work in all lowercase
        sub_pairs = (
            # Blended
            ('casename', 'caseName'),
            ('docketnumber', 'docketNumber'),
            ('datefiled', 'dateFiled'),
            ('suitnature', 'suitNature'),

            # Opinions
            ('lexiscite', 'lexisCite'),
            ('neutralcite', 'neutralCite'),
            ('citecount', 'citeCount'),

            # Oral Args
            ('dateargued', 'dateArgued'),
            ('datereargued', 'dateReargued'),

            # People
            ('DOD', 'dod'),
            ('DOB', 'dob'),

            # RECAP
            ('dateterminated', 'dateTerminated'),
            ('jurydemand', 'juryDemand'),
        )
        for bad, good in sub_pairs:
            q = re.sub(bad, good, q)

        # Make pipes work
        q = re.sub('\|', ' OR ', q)

        return q

    def clean_order_by(self):
        """Sets the default order_by value if one isn't provided by the user."""
        if self.cleaned_data['type'] == 'o' or not self.cleaned_data['type']:
            if not self.cleaned_data['order_by']:
                return self.fields['order_by'].initial
        elif self.cleaned_data['type'] == 'oa':
            if not self.cleaned_data['order_by']:
                return 'dateArgued desc'
        elif self.cleaned_data['type'] == 'p':
            if not self.cleaned_data['order_by']:
                return 'name_reverse asc'
        return self.cleaned_data['order_by']

    def clean_type(self):
        """Make sure that type has an initial value."""
        if not self.cleaned_data['type']:
            return self.fields['type'].initial
        return self.cleaned_data['type']

    def clean(self):
        """
        Handles validation fixes that need to be performed across fields.
        """
        cleaned_data = self.cleaned_data

        # 1. Make sure that the dates do this |--> <--| rather than <--| |-->
        for field_name in self.get_date_field_names():
            before = cleaned_data.get('%s_before' % field_name)
            after = cleaned_data.get('%s_after' % field_name)
            if before and after and (before < after):
                # The user is requesting dates like this: <--b  a-->. Switch
                # the dates so their query is like this: a-->   <--b
                cleaned_data['%s_before' % field_name] = after
                cleaned_data['%s_after' % field_name] = before

        # 2. Convert the value in the court field to the various court_* fields
        court_str = cleaned_data.get('court')
        if court_str:
            if ' ' in court_str:
                court_ids = court_str.split(' ')
            elif ',' in court_str:
                court_ids = court_str.split(',')
            else:
                court_ids = [court_str]
            for court_id in court_ids:
                cleaned_data['court_%s' % court_id] = True

        # 3. Make sure that the user has selected at least one facet for each
        #    taxonomy. Note that this logic must be paralleled in
        #    search_utils.make_facet_variable
        court_bools = [v for k, v in cleaned_data.items()
                       if k.startswith('court_')]
        if not any(court_bools):
            # Set all facets to True
            for key in cleaned_data.keys():
                if key.startswith('court_'):
                    cleaned_data[key] = True

        # 4. Strip any whitespace, otherwise it crashes Solr.
        for k, v in cleaned_data.items():
            if isinstance(v, basestring):
                cleaned_data[k] = v.strip()

        # Here we reset the defaults.
        stat_bools = [v for k, v in cleaned_data.items()
                      if k.startswith('stat_')]
        if not any(stat_bools):
            # Set everything to False...
            for key in cleaned_data.keys():
                if key.startswith('stat_'):
                    cleaned_data[key] = False
            # ...except precedential
            cleaned_data['stat_Precedential'] = True

        return cleaned_data
