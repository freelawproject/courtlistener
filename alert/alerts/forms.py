from django.forms import ModelForm
from alert.userHandling.models import Alert
from django.forms.widgets import HiddenInput, TextInput


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
            'alertText': HiddenInput(),
            'alertName': TextInput(attrs={'class': 'span-5'})
        }
