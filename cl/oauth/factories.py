from factory import Faker
from factory.django import DjangoModelFactory
from oauth2_provider.models import get_application_model

Application = get_application_model()


class ApplicationFactory(DjangoModelFactory):
    """An Application as the DCR endpoint creates it: confidential, no owner."""

    class Meta:
        model = Application

    name = Faker("company")
    client_type = Application.CLIENT_CONFIDENTIAL
    authorization_grant_type = Application.GRANT_AUTHORIZATION_CODE
    redirect_uris = "https://client.example.com/callback"
    algorithm = Application.RS256_ALGORITHM
