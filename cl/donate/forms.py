from django import forms
from django.contrib.auth.models import User
from django.forms import ModelForm
from localflavor.us.forms import USStateField, USZipCodeField
from localflavor.us.us_states import STATE_CHOICES

from cl.donate.models import Donation
from cl.users.models import UserProfile

AMOUNTS = (
    ('5000', '$5,000'),
    ('1000', '$1,000'),
    ('500', '$500'),
    ('250', '$250'),
    ('100', '$100'),
    ('50', '$50'),
    ('25', '$25'),
    ('other', 'Other: $'),
)


class DecimalOrOtherField(forms.DecimalField):
    def __init__(self, *args, **kwargs):
        super(DecimalOrOtherField, self).__init__(*args, **kwargs)

    def to_python(self, value):
        """Makes sure that the value returned is either returned as a decimal
        (as required by amount) or as the word 'other', which is fixed in the
        clean() method for the DonationForm class.
        """
        if value == 'other':
            return value
        else:
            return super(DecimalOrOtherField, self).to_python(value)

    def validate(self, value):
        if value == 'other':
            return value
        else:
            return super(DecimalOrOtherField, self).validate(value)


class ProfileForm(ModelForm):
    wants_newsletter = forms.BooleanField(
        required=False,
    )
    STATE_CHOICES = list(STATE_CHOICES)
    STATE_CHOICES.insert(0, ('', '---------'))
    state = USStateField(
        widget=forms.Select(
            choices=STATE_CHOICES,
            attrs={'class': 'form-control'}
        )
    )
    zip_code = USZipCodeField(
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    class Meta:
        model = UserProfile
        fields = (
            'address1',
            'address2',
            'city',
            'state',
            'zip_code',
            'wants_newsletter',
        )
        widgets = {
            'address1': forms.TextInput(attrs={'class': 'form-control'}),
            'address2': forms.TextInput(attrs={'class': 'form-control'}),
            'city': forms.TextInput(attrs={'class': 'form-control'}),
            'zip_code': forms.TextInput(attrs={'class': 'form-control'})
        }

    def __init__(self, *args, **kwargs):
        super(ProfileForm, self).__init__(*args, **kwargs)
        self.fields['wants_newsletter'].label = "Send me the monthly Free Law Project newsletter"
        for key in ['address1', 'city', 'state', 'zip_code']:
            self.fields[key].required = True


class UserForm(ModelForm):
    class Meta:
        model = User
        fields = (
            'first_name',
            'last_name',
            'email',
        )
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'})
        }

    def __init__(self, *args, **kwargs):
        super(UserForm, self).__init__(*args, **kwargs)
        # Make all fields required on the donation form
        for key in self.fields:
            self.fields[key].required = True


class DonationForm(ModelForm):
    amount_other = forms.DecimalField(
        required=False,
    )
    amount = DecimalOrOtherField(
        widget=forms.RadioSelect(
            choices=AMOUNTS,
        ),
        initial='50',
    )

    class Meta:
        model = Donation
        fields = (
            'amount_other',
            'amount',
            'payment_provider',
            'send_annual_reminder',
            'referrer',
        )
        widgets = {
            'payment_provider': forms.RadioSelect(),
            'referrer': forms.HiddenInput(),
        }

    def clean(self):
        """
        Handles validation fixes that need to be performed across fields.
        """
        # 1. Set the amount field to amount_other field's value
        if self.cleaned_data.get('amount') == 'other':
            self.cleaned_data['amount'] = self.cleaned_data.get('amount_other')
        return self.cleaned_data
