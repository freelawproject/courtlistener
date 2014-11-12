from django.forms import ModelForm
from django.forms.widgets import HiddenInput, TextInput, Select, CheckboxInput
from alert.userHandling.models import Alert


class CreateAlertForm(ModelForm):
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
