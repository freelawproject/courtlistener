from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.utils.text import slugify
from factory import (
    Faker,
    LazyAttribute,
    LazyAttributeSequence,
    LazyFunction,
    RelatedFactory,
    SubFactory,
)
from factory.django import DjangoModelFactory
from pytz import utc

from cl.users.models import EmailSent, UserProfile


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User

    class Params:
        # Faker's `user_name` and `email` providers draw from a namespace small
        # enough (~16 bits) to repeat at our test sample sizes, which trips the
        # unique constraint on `auth_user.username`. Derive both from the
        # sequence counter instead: unique by construction, and computed once
        # here so the two stay in sync. Excluded from the model's fields.
        name_slug = LazyAttributeSequence(
            lambda o, n: f"{slugify(o.first_name)}.{slugify(o.last_name)}.{n}"
        )

    username = LazyAttribute(lambda o: o.name_slug)
    first_name = Faker("first_name")
    last_name = Faker("last_name")
    email = LazyAttribute(lambda o: f"{o.name_slug}@example.com")
    # If you override this, be sure to use make_password or else you'll just
    # put your string password into the DB without hashing and salting it and
    # you'll wonder why it doesn't work.
    password = LazyFunction(lambda: make_password("password"))
    is_staff = False
    is_superuser = False
    is_active = True


class UserWithChildProfileFactory(UserFactory):
    profile = RelatedFactory(
        "cl.users.factories.UserProfileFactory",
        factory_related_name="user",
    )


class EmailSentFactory(DjangoModelFactory):
    class Meta:
        model = EmailSent


class UserProfileFactory(DjangoModelFactory):
    class Meta:
        model = UserProfile

    email_confirmed = True
    key_expires = Faker(
        "date_time_this_year",
        before_now=False,
        after_now=True,
        tzinfo=utc,
    )
    activation_key = Faker(
        "password",
        length=40,
        special_chars=False,
        upper_case=False,
        lower_case=False,
    )


class UserProfileWithParentsFactory(UserProfileFactory):
    user = SubFactory(UserFactory)
