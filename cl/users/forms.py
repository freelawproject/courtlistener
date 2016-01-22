from cl.users.models import UserProfile
from django import forms
from django.contrib.auth.forms import UserCreationForm, PasswordChangeForm, \
    PasswordResetForm, SetPasswordForm
from django.contrib.auth.models import User
from django.forms import ModelForm
from localflavor.us.forms import USStateField, USZipCodeField
from localflavor.us.us_states import STATE_CHOICES

# Many forms in here use unusual autocomplete attributes. These conform with
# https://html.spec.whatwg.org/multipage/forms.html#autofill, and enables them
# to be autofilled in various ways.


class ProfileForm(ModelForm):
    STATE_CHOICES = list(STATE_CHOICES)
    STATE_CHOICES.insert(0, ('', '---------'))
    state = USStateField(
        widget=forms.Select(
            choices=STATE_CHOICES,
            attrs={
                'class': 'form-control',
                'autocomplete': 'address-level1',
            },
        ),
        required=False,
    )
    zip_code = USZipCodeField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'autocomplete': 'postal-code',
        }),
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
            'employer': forms.TextInput(attrs={
                'class': 'form-control',
                'autocomplete': 'organization',
            }),
            'barmembership': forms.SelectMultiple(
                attrs={'size': '8', 'class': 'form-control'}
            ),
            'address1': forms.TextInput(attrs={
                'class': 'form-control',
                'autocomplete': 'address-line1',
            }),
            'address2': forms.TextInput(attrs={
                'class': 'form-control',
                'autocomplete': 'address-line2',
            }),
            'city': forms.TextInput(attrs={
                'class': 'form-control',
                'autocomplete': 'address-level2',
            }),
    #        'wants_newsletter': forms.TextInput(attrs={'class': 'form-control'}),
    #        'plaintext_preferred': forms.TextInput(attrs={'class': 'form-control'}),
        }


class UserForm(ModelForm):
    email = forms.EmailField(
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'autocomplete': 'email',
        })
    )

    class Meta:
        model = User
        fields = (
            'first_name',
            'last_name',
            'email',
        )
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'autocomplete': 'given-name',
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'autocomplete': 'family-name',
            }),
        }


class UserCreationFormExtended(UserCreationForm):
    def __init__(self, *args, **kwargs):
        """A bit of an unusual form because instead of creating it ourselves,
        we are overriding the one from Django. Thus, instead of declaring
        everything explicitly like we normally do, we just override the
        specific parts we want to, after calling the super class's __init__().
        """
        super(UserCreationFormExtended, self).__init__(*args, **kwargs)

        self.fields['username'].label = 'User Name*'
        self.fields['email'].label = "Email Address*"
        self.fields['password1'].label = "Password*"
        self.fields['password2'].label = "Confirm Password*"
        self.fields['first_name'].label = "First Name"
        self.fields['last_name'].label = "Last Name"

        # Give all fields a form-control class.
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})

        self.fields['username'].widget.attrs.update({
            'class': 'auto-focus form-control',
            'autocomplete': 'username',
        })
        self.fields['email'].required = True
        self.fields['email'].widget.attrs.update({
            'autocomplete': 'email',
        })
        self.fields['password1'].widget.attrs.update({
            'autocomplete': 'new-password',
        })
        self.fields['password2'].widget.attrs.update({
            'autocomplete': 'new-password',
        })
        self.fields['first_name'].widget.attrs.update({
            'autocomplete': 'given-name',
        })
        self.fields['last_name'].widget.attrs.update({
            'autocomplete': 'family-name',
        })

    class Meta:
        model = User
        fields = (
            'username',
            'email',
            'first_name',
            'last_name',
        )


class EmailConfirmationForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control auto-focus input-lg',
            'placeholder': "Your Email Address",
            'autocomplete': 'email',
        }),
        required=True,
    )


class CustomPasswordChangeForm(PasswordChangeForm):
    """
    A form that lets a user change his/her password by entering
    their old password. Overrides Django default form to allow
    the customization of attributes.
    """
    old_password = forms.CharField(
        label="Old password",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'autocomplete': 'current-password',
        }),
    )
    new_password1 = forms.CharField(
        label="New password",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'autocomplete': 'new-password',
        }),
    )
    new_password2 = forms.CharField(
        label="New password confirmation",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'autocomplete': 'new-password',
        }),
    )


class CustomPasswordResetForm(PasswordResetForm):
    """A simple subclassing of a Django form in order to change class
    attributes.
    """
    def __init__(self, *args, **kwargs):
        super(CustomPasswordResetForm, self).__init__(*args, **kwargs)

        self.fields['email'].widget.attrs.update(
            {
                'class': 'auto-focus form-control input-lg',
                'placeholder': 'Your Email Address',
                'autocomplete': 'email',
            }
        )


class CustomSetPasswordForm(SetPasswordForm):
    """A simple subclassing of a Django form in order to change class
    attributes.
    """
    def __init__(self, user, *args, **kwargs):
        super(CustomSetPasswordForm, self).__init__(user, *args, **kwargs)

        self.fields['new_password1'].widget.attrs.update({
            'class': 'auto-focus form-control',
            'autocomplete': 'new-password',
        })
        self.fields['new_password2'].widget.attrs.update({
            'class': 'form-control',
            'autocomplete': 'new-password',
        })
