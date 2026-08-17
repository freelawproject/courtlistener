from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.utils.text import slugify
from factory import (
    Faker,
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

    # Faker's `user_name` provider only gives us about 16 bits of entropy (a
    # first and/or last name, plus at most two digits or one letter), so a test
    # that creates a couple dozen users has a real chance of drawing the same
    # name twice and violating the unique constraint on `auth_user.username`.
    # Deriving it from the factory's sequence counter instead keeps the
    # username human-readable while making it unique by construction.
    username = LazyAttributeSequence(
        lambda o, n: f"{slugify(o.first_name)}.{slugify(o.last_name)}.{n}"
    )
    first_name = Faker("first_name")
    last_name = Faker("last_name")
    email = Faker("email")
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
