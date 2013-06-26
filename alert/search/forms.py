from alert.search.fields import CeilingDateField
from alert.search.fields import FloorDateField
from alert.search.models import Court
from alert.search.models import DOCUMENT_STATUSES
from django import forms

import re

SORT_CHOICES = (
    ('score desc', 'Relevance'),
    ('dateFiled desc', 'Newest first'),
    ('dateFiled asc', 'Oldest first'),
    ('citeCount desc', 'Most cited first'),
    ('citeCount asc', 'Least cited first'),
)

INPUT_FORMATS = [
    '%Y-%m-%d',  # '2006-10-25'
    '%Y-%m',     # '2006-10'
    '%Y',        # '2006'
    '%m-%d-%Y',  # '10-25-2006'
    '%m-%Y',     # '10-2006'
    '%m-%d-%y',  # '10-25-06'
    '%m-%y',     # '10-06'
    '%m/%d/%Y',  # '10/25/2006'
    '%m/%Y',     # '10/2006'
    '%m/%d/%y',  # '10/25/06'
    '%m/%y',     # '10/06'
    '%Y/%m/%d',  # '2006/10/26'
    '%Y/%m',     # '2006/10'
]


class SearchForm(forms.Form):
    q = forms.CharField(
        required=False,
        initial='*:*'
    )
    sort = forms.ChoiceField(
        choices=SORT_CHOICES,
        required=False,
        initial='dateFiled desc',
        widget=forms.Select(
            attrs={'class': 'external-input',
                   'tabindex': '9'}
        )
    )
    case_name = forms.CharField(
        required=False,
        initial='',
        widget=forms.TextInput(
            attrs={'class': 'span-5 external-input',
                   'autocomplete': 'off',
                   'tabindex': '10'}
        )
    )
    judge = forms.CharField(
        required=False,
        initial='',
        widget=forms.TextInput(
            attrs={'class': 'span-5 external-input',
                   'autocomplete': 'off',
                   'tabindex': '11'}
        )
    )
    court_all = forms.BooleanField(
        label='All Courts / Clear',
        required=False,
        initial=True,
        widget=forms.CheckboxInput(
            attrs={'checked': 'checked',
                   'class': 'external-input court-checkbox left'}
        )
    )
    filed_after = FloorDateField(
        required=False,
        input_formats=INPUT_FORMATS,
        widget=forms.TextInput(
            attrs={'placeholder': 'YYYY-MM-DD',
                   'class': 'span-3 external-input',
                   'autocomplete': 'off'}
        )
    )
    filed_before = CeilingDateField(
        required=False,
        input_formats=INPUT_FORMATS,
        widget=forms.TextInput(
            attrs={'placeholder': 'YYYY-MM-DD',
                   'class': 'span-3 external-input',
                   'autocomplete': 'off'}
        )
    )
    west_cite = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={'class': 'span-5 external-input',
                   'autocomplete': 'off'}
        )
    )
    neutral_cite = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={'class': 'span-5 external-input',
                   'autocomplete': 'off'}
        )
    )
    docket_number = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={'class': 'span-5 external-input',
                   'autocomplete': 'off'}
        )
    )
    cited_gt = forms.CharField(
        required=False,
        initial=0,
        widget=forms.HiddenInput(
            attrs={'class': 'external-input'}
        )
    )
    cited_lt = forms.CharField(
        required=False,
        initial=10000,
        widget=forms.HiddenInput(
            attrs={'class': 'external-input'}
        )
    )

    def __init__(self, *args, **kwargs):
        super(SearchForm, self).__init__(*args, **kwargs)
        """Normally we wouldn't need to use __init__ in a form object like this, however, since we are generating
        checkbox fields with dynamic names coming from the database, we need to interact directly with the fields dict.
        If it were possible to dynamically generate variable names (without using exec), we could do this work without
        init, but since it's "only" possible to dynamically generate dict keys (as done below), we have to work directly
        with the fields dict, which is available only in init. So it goes...
        """

        # Query the DB so we can build up check boxes for each court in use.
        courts = Court.objects.filter(in_use=True).values_list('courtUUID', 'short_name')

        for court in courts:
            self.fields['court_' + court[0]] = forms.BooleanField(
                label=court[1],
                required=False,
                initial=True,
                widget=forms.CheckboxInput(attrs={'checked': 'checked'})
            )
        for status in DOCUMENT_STATUSES:
            if status[1] == 'Precedential':
                initial = True
                attrs = {'checked': 'checked'}
            else:
                initial = False
                attrs = {}
            self.fields['stat_' + status[1]] = forms.BooleanField(
                label=status[1],
                required=False,
                initial=initial,
                widget=forms.CheckboxInput(attrs=attrs)
            )

    def clean_q(self):
        """
        Cleans up various problems with the query:
         - '' --> '*:*'
         - lowercase --> camelCase
         - '|' --> ' OR '
        """
        q = self.cleaned_data['q']

        if q == '' or q == '*':
            q = '*:*'

        # Fix fields to work in all lowercase
        q = re.sub('casename', 'caseName', q)
        q = re.sub('lexiscite', 'lexisCite', q)
        q = re.sub('westcite', 'westCite', q)
        q = re.sub('casenumber', 'caseNumber', q)
        q = re.sub('docketnumber', 'docketNumber', q)
        q = re.sub('neutralcite', 'neutralCite', q)
        q = re.sub('citecount', 'citeCount', q)

        # Make pipes work
        q = re.sub('\|', ' OR ', q)

        return q

    def clean(self):
        """
        Handles validation fixes that need to be performed across fields.
        """
        cleaned_data = self.cleaned_data

        # 1. Make sure that the dates do this |--> <--| rather than <--| |-->
        before = cleaned_data.get('filed_before')
        after = cleaned_data.get('filed_after')
        if before and after:
            # Only do something if both fields are valid so far.
            if before < after:
                # The user is requesting dates like this: <--b  a-->. Switch
                # the dates so their query is like this: a-->   <--b
                cleaned_data['filed_before'] = after
                cleaned_data['filed_after'] = before

        # 2. Make sure that the user has selected at least one facet for each
        #    taxonomy.
        court_bools = [v for k, v in cleaned_data.iteritems()
                       if k.startswith('court_')]
        if not any(court_bools):
            # Set all facets to true
            for key in cleaned_data.iterkeys():
                if key.startswith('court_'):
                    cleaned_data[key] = True

        stat_bools = [v for k, v in cleaned_data.iteritems()
                      if k.startswith('stat_')]
        if not any(stat_bools):
            # Set all facets to true
            for key in cleaned_data.iterkeys():
                if key.startswith('stat_'):
                    cleaned_data[key] = True

        return cleaned_data
