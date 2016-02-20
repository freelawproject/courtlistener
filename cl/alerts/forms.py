from django.conf import settings
from django.core.exceptions import ValidationError
from django.forms import ModelForm
from django.forms.widgets import HiddenInput, TextInput, Select, CheckboxInput
from cl.alerts.models import Alert


class CreateAlertForm(ModelForm):
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super(CreateAlertForm, self).__init__(*args, **kwargs)

    def clean_rate(self):
        rate = self.cleaned_data['rate']
        not_donated_enough = self.user.profile.total_donated_last_year < \
            settings.MIN_DONATION['rt_alerts']
        if rate == 'rt' and not_donated_enough:
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
        exclude = ('user',)
        fields = (
            'name',
            'query',
            'rate',
            'always_send_email',
        )
        widgets = {
            'query': HiddenInput(
                attrs={
                    'tabindex': '250'
                }
            ),
            'name': TextInput(
                attrs={
                    'class': 'form-control',
                    'tabindex': '251'
                }
            ),
            'rate': Select(
                attrs={
                    'class': 'form-control',
                    'tabindex': '252',
                }
            ),
            'always_send_email': CheckboxInput(
                attrs={
                    'tabindex': '253',
                }

            ),
        }
