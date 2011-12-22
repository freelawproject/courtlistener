# This software and any associated files are copyright 2010 Brian Carver and
# Michael Lissner.
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


from alert.search.models import Court
from django import forms

REFINE_CHOICES = (
        ('new', 'New search'),
        ('refine', 'In current results'),
    )

SORT_CHOICES = (
        ('score asc', 'Relevance'),
        ('dateFiled desc', 'Date: newest first'),
        ('dateFiled asc', 'Date: oldest first'),
    )

class SearchForm(forms.Form):
    q = forms.CharField(required=False, initial='*')
    sort = forms.ChoiceField(
                         choices=SORT_CHOICES,
                         initial='rel',
                         required=False,
                         widget=forms.Select(
                                   attrs={'class': 'external-input'}))
    case_name = forms.CharField(
                        required=False,
                        widget=forms.TextInput(
                                   attrs={'class': 'span-5 external-input'}))
    status_p = forms.BooleanField(required=False, initial=True)
    status_u = forms.BooleanField(required=False, initial=True)
    filed_before = forms.DateTimeField(
                        required=False,
                        widget=forms.TextInput(
                                   attrs={'placeholder': 'YYYY-MM-DD'}))
    filed_after = forms.DateTimeField(
                        required=False,
                        widget=forms.TextInput(
                                   attrs={'placeholder': 'YYYY-MM-DD'}))
    west_cite = forms.CharField(required=False)
    docket_number = forms.CharField(required=False)
    court_all = forms.BooleanField(required=False, initial=True)


    def __init__(self, data={}, *args, **kwargs):
        super(SearchForm, self).__init__(data, *args, **kwargs)
        if data.get('sort') is not None:
            # If there's a query, add the refine field.
            self.fields['refine'] = forms.ChoiceField(
                                              choices=REFINE_CHOICES,
                                              required=False,
                                              widget=forms.RadioSelect())

        # Query the DB, and build up check boxes for each court that's in use.  
        # See: http://stackoverflow.com/questions/8556844 and 
        # http://jacobian.org/writing/dynamic-form-generation/
        courts = Court.objects.filter(in_use=True).values_list(
                                                    'courtUUID', 'short_name')
        for court in courts:
            self.fields[court[0]] = forms.BooleanField(
                                              label=court[1],
                                              required=False,
                                              initial=True)


    def clean_q(self):
        '''
        Cleans up various problems with the query:
         - '' --> '*'
        
        '''
        q = self.cleaned_data['q']

        if q == '' :
            return '*'
        else:
            return q

    '''
    TODO: Add validation rules here:
        - parse out invalid fields
        - use label_suffix='' to eliminate colons
        - use auto_id to change the labels/ids
    '''
