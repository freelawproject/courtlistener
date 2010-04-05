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
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.forms import ModelForm
from alert.userHandling.models import UserProfile

class ProfileForm(ModelForm):
    class Meta:
        model = UserProfile
        # things MUST be excluded, or they get deleted. Creates confusing
        # deletions. 
        exclude = ('user','alert', 'avatar',)

        
class UserForm(ModelForm):
    email = forms.EmailField(required=True)
    class Meta:
        model = User
        # If these aren't excluded, they throw errors or get reset to default. 
        # Either is BAD, BAD, BAD
        exclude = ('username', 'password', 'last_login', 'date_joined',
            'is_staff', 'is_active', 'is_superuser', 'groups', 'user_permissions',)
            

class UserCreationFormExtended(UserCreationForm):

    def __init__(self, *args, **kwargs):
        super(UserCreationFormExtended, self).__init__(*args, **kwargs)
        self.fields['email'].required = True

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name') 
