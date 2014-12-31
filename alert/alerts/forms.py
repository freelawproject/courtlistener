from django.core.exceptions import ValidationError
from django.forms import ModelForm
from django.forms.widgets import HiddenInput, TextInput, Select, CheckboxInput
from alert.userHandling.models import Alert


class CreateAlertForm(ModelForm):
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super(CreateAlertForm, self).__init__(*args, **kwargs)

    def clean_alertFrequency(self):
        rate = self.cleaned_data['alertFrequency']
        if rate == 'rt' and self.user.profile.total_donated_last_year < 10:
            # Somebody is trying to hack past the JS/HTML block on the front
            # end. Don't let them create the alert until they've donated.
            raise ValidationError(
                u'You must donate more than $10 per year to create Real Time '
                u'alerts.'
            )
        else:
            return rate

    class Meta:
        model = Alert
        fields = (
            'alertName',
            'alertText',
            'alertFrequency',
            'sendNegativeAlert',
        )
        widgets = {
            'alertText': HiddenInput(
                attrs={
                    'tabindex': '250'
                }
            ),
            'alertName': TextInput(
                attrs={
                    'class': 'form-control',
                    'tabindex': '251'
                }
            ),
            'alertFrequency': Select(
                attrs={
                    'class': 'form-control',
                    'tabindex': '252',
                }
            ),
            'sendNegativeAlert': CheckboxInput(
                attrs={
                    'tabindex': '253',
                }

            ),
        }
