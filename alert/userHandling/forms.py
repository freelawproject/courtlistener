from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.contrib.localflavor.us.forms import USStateField, USZipCodeField
from django.contrib.localflavor.us.us_states import STATE_CHOICES
from django.forms import ModelForm
from alert.userHandling.models import UserProfile


class ProfileForm(ModelForm):
    STATE_CHOICES = list(STATE_CHOICES)
    STATE_CHOICES.insert(0, ('', '---------'))
    state = USStateField(
        widget=forms.Select(
            choices=STATE_CHOICES,
            attrs={'class': 'span-5'}
        ),
        required=False,
    )
    zip_code = USZipCodeField(
        widget=forms.TextInput(
            attrs={'class': 'span-4'}
        ),
        required=False,
    )

    class Meta:
        model = UserProfile
        fields = (
            'employer',
            'address1',
            'address2',
            'city',
            'state',
            'zip_code',
            'wants_newsletter',
            'barmembership',
            'plaintext_preferred',
        )
        widgets = {
            'employer': forms.TextInput(
                attrs={'class': 'span-9'}
            ),
            'barmembership': forms.SelectMultiple(
                attrs={'class': 'span-9',
                       'size': '8'}
            ),
            'address1': forms.TextInput(
                attrs={'class': 'span-9'}
            ),
            'address2': forms.TextInput(
                attrs={'class': 'span-9'}
            ),
            'city': forms.TextInput(
                attrs={'class': 'span-9'}
            ),
        }


class UserForm(ModelForm):
    email = forms.EmailField(
        required=True,
        widget=forms.TextInput(
            attrs={'class': 'span-9'}
        )
    )

    class Meta:
        model = User
        fields = (
            'first_name',
            'last_name',
            'email',
        )
        widgets = {
            'first_name': forms.TextInput(
                attrs={'class': 'span-4'}
            ),
            'last_name': forms.TextInput(
                attrs={'class': 'span-5'}
            ),
        }


class UserCreationFormExtended(UserCreationForm):
    def __init__(self, *args, **kwargs):
        super(UserCreationFormExtended, self).__init__(*args, **kwargs)
        self.fields['email'].required = True

    class Meta:
        model = User
        fields = (
            'username',
            'email',
            'first_name',
            'last_name'
        )


class EmailConfirmationForm(forms.Form):
    email = forms.EmailField()
