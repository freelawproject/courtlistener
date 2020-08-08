from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient


def make_client(user_pk):
    user = User.objects.get(pk=user_pk)
    token, created = Token.objects.get_or_create(user=user)
    token_header = "Token %s" % token
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=token_header)
    return client
