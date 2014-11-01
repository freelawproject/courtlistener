from django.forms import ModelForm
from django.forms.widgets import HiddenInput, TextInput, Select
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
            'alertText': HiddenInput(),
            'alertName': TextInput(attrs={'class': 'form-control'}),
            'alertFrequency': Select(attrs={'class': 'form-control'})
        }
