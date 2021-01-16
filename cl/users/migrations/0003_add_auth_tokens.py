# -*- coding: utf-8 -*-


from django.contrib.auth.models import User
from django.db import migrations, models
from rest_framework.authtoken.models import Token


def add_tokens(apps, schema_editor):
    print("Adding auth tokens for the API...")
    for user in User.objects.all():
        Token.objects.get_or_create(user=user)

def remove_tokens(apps, schema_editor):
    print("Deleting all auth tokens for the API...")
    Token.objects.all().delete()

class Migration(migrations.Migration):

    dependencies = [
        ('users', '0002_load_initial_data'),
    ]

    operations = [
        migrations.RunPython(add_tokens, reverse_code=remove_tokens),
    ]
