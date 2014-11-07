from django.contrib.auth.hashers import MAXIMUM_PASSWORD_LENGTH
from alert.userHandling.models import UserProfile
from django import forms
from django.contrib.auth.forms import UserCreationForm, PasswordChangeForm
from django.contrib.auth.models import User
from django.forms import ModelForm
from localflavor.us.forms import USStateField, USZipCodeField
from localflavor.us.us_states import STATE_CHOICES


class ProfileForm(ModelForm):
    STATE_CHOICES = list(STATE_CHOICES)
    STATE_CHOICES.insert(0, ('', '---------'))
    state = USStateField(
        widget=forms.Select(
            choices=STATE_CHOICES,
            attrs={'class': 'form-control'}
        ),
        required=False,
    )
    zip_code = USZipCodeField(
        widget=forms.TextInput(attrs={'class': 'form-control'}),
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
            'employer': forms.TextInput(attrs={'class': 'form-control'}),
            'barmembership': forms.SelectMultiple(
                attrs={'size': '8', 'class': 'form-control'}
            ),
            'address1': forms.TextInput(attrs={'class': 'form-control'}),
            'address2': forms.TextInput(attrs={'class': 'form-control'}),
            'city': forms.TextInput(attrs={'class': 'form-control'}),
    #        'wants_newsletter': forms.TextInput(attrs={'class': 'form-control'}),
    #        'plaintext_preferred': forms.TextInput(attrs={'class': 'form-control'}),
        }


class UserForm(ModelForm):
    email = forms.EmailField(
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    class Meta:
        model = User
        fields = (
            'first_name',
            'last_name',
            'email',
        )
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
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


class CustomPasswordChangeForm(PasswordChangeForm):
    """
    A form that lets a user change his/her password by entering
    their old password. Overrides Django default form to allow
    the customization of class attributes.
    """
    old_password = forms.CharField(
        label="Old password",
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        max_length=MAXIMUM_PASSWORD_LENGTH,
    )
    new_password1 = forms.CharField(
        label="New password",
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        max_length=MAXIMUM_PASSWORD_LENGTH,
    )
    new_password2 = forms.CharField(
        label="New password confirmation",
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        max_length=MAXIMUM_PASSWORD_LENGTH,
    )
