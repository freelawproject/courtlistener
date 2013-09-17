from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.utils.translation import ugettext_lazy as _
from django import forms


class ConfirmedEmailAuthenticationForm(AuthenticationForm):
    """Your average form, but with an additional tweak to the clean method which ensures that only users with
    confirmed email addresses can log in."""
    def __init__(self, *args, **kwargs):
        super(ConfirmedEmailAuthenticationForm, self).__init__(*args, **kwargs)

    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if username and password:
            self.user_cache = authenticate(username=username, password=password)
            if self.user_cache is None:
                raise forms.ValidationError(
                    _("Please enter a correct username and password. Note that both fields are case-sensitive."))
            elif not self.user_cache.is_active:
                raise forms.ValidationError(_("This account is inactive."))
            elif not self.user_cache.get_profile().email_confirmed:
                raise forms.ValidationError('Please <a href="/email-confirmation/request/">validate your email address</a> to log in.')
        self.check_for_test_cookie()
        return self.cleaned_data
