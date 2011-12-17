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


SORT_CHOICES = (
        ('rel', 'Relevance'),
        ('date-desc', 'Date: newest first'),
        ('date-asc', 'Date: oldest first'),
    )

class SearchForm(forms.Form):
    q = forms.CharField()
    refine = forms.BooleanField()
    sort = forms.ChoiceField(choices=SORT_CHOICES)
    case_name = forms.CharField()
    status_p = forms.BooleanField()
    status_u = forms.BooleanField()
    court_all = forms.BooleanField()
    courts = Court.objects.filter(in_use=True).order_by('order')
    for court in courts:
        court.courtUUID = forms.BooleanField()

    class Meta:
        widgets = {
                   'refine': forms.RadioSelect,
                   'status_p': forms.CheckboxInput,
                   'status_u': forms.CheckboxInput
                 }
