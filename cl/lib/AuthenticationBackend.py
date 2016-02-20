from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm
from django import forms
from django.core.urlresolvers import reverse


class ConfirmedEmailAuthenticationForm(AuthenticationForm):
    """Your average form, but with an additional tweak to the clean method
    which ensures that only users with confirmed email addresses can log in.

    This is needed because we create stub accounts for people that donate and
    don't already have accounts. Without this check, people could sign up for
    accounts, log in, and see the donations of somebody that previously only
    had a stub account.
    """
    def __init__(self, *args, **kwargs):
        super(ConfirmedEmailAuthenticationForm, self).__init__(*args, **kwargs)

    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if username and password:
            self.user_cache = authenticate(username=username, password=password)
            if self.user_cache is None:
                raise forms.ValidationError(
                    self.error_messages['invalid_login'],
                    code='invalid_login',
                    params={'username': self.username_field.verbose_name},
                )
            elif not self.user_cache.is_active:
                raise forms.ValidationError(
                    self.error_messages['inactive'],
                    code='inactive',
                )
            elif not self.user_cache.profile.email_confirmed:
                raise forms.ValidationError(
                    'Please <a href="%s">validate your email address</a> to '
                    'log in.' % reverse('email_confirmation_request')
                )

        return self.cleaned_data
