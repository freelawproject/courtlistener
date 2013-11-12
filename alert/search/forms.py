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

# Query the DB so we can build up check boxes for each court in use.
COURTS = Court.objects.filter(in_use=True).values('pk', 'short_name', 'jurisdiction')


def _clean_form(request, cd):
    """Returns cleaned up values as a Form object.
    """
    # Make a copy of request.GET so it is mutable
    mutable_get = request.GET.copy()

    # Send the user the cleaned up query
    mutable_get['q'] = cd['q']
    if mutable_get.get('filed_before') and cd.get('filed_before') is not None:
        # Don't use strftime since it won't work prior to 1900.
        before = cd['filed_before']
        mutable_get['filed_before'] = '%s-%02d-%02d' % \
                                      (before.year, before.month, before.day)
    if mutable_get.get('filed_after') and cd.get('filed_before') is not None:
        after = cd['filed_after']
        mutable_get['filed_after'] = '%s-%02d-%02d' % \
                                     (after.year, after.month, after.day)
    mutable_get['sort'] = cd['sort']

    for court in COURTS:
        mutable_get['court_%s' % court['pk']] = cd['court_%s' % court['pk']]

    return SearchForm(mutable_get)


class SearchForm(forms.Form):
    q = forms.CharField(
        required=False
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
    court = forms.CharField(
        required=False,
        widget=forms.HiddenInput()
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
    citation = forms.CharField(
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
        initial=15000,
        widget=forms.HiddenInput(
            attrs={'class': 'external-input'}
        )
    )

    def __init__(self, *args, **kwargs):
        super(SearchForm, self).__init__(*args, **kwargs)
        """Normally we wouldn't need to use __init__ in a form object like this, however, since we are generating
        checkbox fields with dynamic names coming from the database, we need to interact directly with the fields dict.
        """

        for court in COURTS:
            self.fields['court_' + court['pk']] = forms.BooleanField(
                label=court['short_name'],
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

    # This is a particularly nasty area of the code due to several factors:
    #  1. Django doesn't have a good method of setting default values for bound forms. As a result, we set them here as
    #     part of a cleanup routine. This way a user can do a query for page=2, and still have all the correct
    #     defaults.
    #  2. In our search form, part of what we do is clean up the GET requests that the user sent. This is completed in
    #     _clean_form(). This allows a user to be taught what better queries look like. To do this, we have to
    #     make a temporary variable in _clean_form() and assign it the values of the cleaned_data. The upshot of this
    #     is that most changes made here will also need to be made in _clean_form(). Failure to do that will result in
    #     the query being processed correctly (search results are all good), but the form on the UI won't be cleaned up
    #     for the user, making things rather confusing.
    #  3. We do some cleanup work in search_utils.make_stats_variable(). The work that's done there is used to check
    #     or uncheck the boxes in the sidebar, so if you tweak how they work you'll need to tweak this function.
    # In short: This is a nasty area. Comments this long are a bad sign for the intrepid developer.
    def clean_q(self):
        """
        Cleans up various problems with the query:
         - lowercase --> camelCase
         - '|' --> ' OR '
        """
        q = self.cleaned_data['q']

        # Fix fields to work in all lowercase
        q = re.sub('casename', 'caseName', q)
        q = re.sub('lexiscite', 'lexisCite', q)
        q = re.sub('westcite', 'westCite', q)  # Purge after 2014-08-06
        q = re.sub('casenumber', 'caseNumber', q)
        q = re.sub('docketnumber', 'docketNumber', q)
        q = re.sub('neutralcite', 'neutralCite', q)
        q = re.sub('citecount', 'citeCount', q)

        # Make pipes work
        q = re.sub('\|', ' OR ', q)

        return q

    def clean_sort(self):
        """Sets the default sort value if one isn't provided by the user."""
        if not self.cleaned_data['sort']:
            return self.fields['sort'].initial
        return self.cleaned_data['sort']

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

        # 2. Convert the value in the court field to the various court_* fields
        court_str = cleaned_data.get('court')
        if court_str:
            if ' ' in court_str:
                court_ids = court_str.split(' ')
            elif ',' in court_str:
                court_ids = court_str.split(',')
            for id in court_ids:
                cleaned_data['court_%s' % id] = True

        # 3. Make sure that the user has selected at least one facet for each
        #    taxonomy. Note that this logic must be paralleled in search_utils.make_facet_variable
        court_bools = [v for k, v in cleaned_data.iteritems()
                       if k.startswith('court_')]
        if not any(court_bools):
            # Set all facets to true
            for key in cleaned_data.iterkeys():
                if key.startswith('court_'):
                    cleaned_data[key] = True

        # Here we reset the defaults.
        stat_bools = [v for k, v in cleaned_data.iteritems()
                      if k.startswith('stat_')]
        if not any(stat_bools):
            # Set everything to False...
            for key in cleaned_data.iterkeys():
                if key.startswith('stat_'):
                    cleaned_data[key] = False
            # ...except precedential
            cleaned_data['stat_Precedential'] = True

        return cleaned_data
