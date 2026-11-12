"""Django app configuration for single sign-on."""

from django.apps import AppConfig


class SSOConfig(AppConfig):
    """The single sign-on app."""

    name = "cl.sso"
    verbose_name = "Single sign-on"
