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


from django import forms
from django.forms import ModelForm
from alert.favorites.models import Favorite

# Used in the favorite forms.
class FavoriteForm(ModelForm):
    class Meta:
        model = Favorite
        widgets = {
            'id'     : forms.HiddenInput(),
            'doc_id' : forms.HiddenInput(),
            'name'   : forms.TextInput(attrs={
                            'class' : 'span-10 last',
                            'id' : 'save-favorite-name-field',
                            'tabindex' : '1',
                            'maxlength': '100'}),
            'notes'  : forms.Textarea(attrs={
                            'class' : 'span-10 last bottom',
                            'id' : 'save-favorite-notes-field',
                            'tabindex': '2',
                            'maxlength' : '600'})
        }
