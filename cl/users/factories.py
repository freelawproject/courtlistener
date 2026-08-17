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


def _name_slug(user, n: int) -> str:
    """Build a unique, human-readable handle from a user's name.

    Faker's `user_name` and `email` providers both draw from a small namespace
    (a first and/or last name, plus at most two digits or one letter — about 16
    bits), which is not enough for the sample sizes our tests use. Appending
    the factory's sequence counter makes the result unique by construction
    rather than merely unlikely to repeat.

    :param user: the factory stub holding the already-resolved name fields
    :param n: the factory's sequence counter for this object
    :return: a slug of the form "first.last.7"
    """
    return f"{slugify(user.first_name)}.{slugify(user.last_name)}.{n}"


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User

    # `auth_user.username` is unique, so drawing this from Faker meant a test
    # that created a couple dozen users could collide and die with an
    # IntegrityError. See `_name_slug` above.
    username = LazyAttributeSequence(_name_slug)
    first_name = Faker("first_name")
    last_name = Faker("last_name")
    # `User.email` has no unique constraint, so a duplicate here fails silently
    # rather than loudly: it makes the code paths that branch on an address
    # being attached to more than one account behave differently than the test
    # intended. Keep it unique, and in sync with the username.
    email = LazyAttributeSequence(
        lambda o, n: f"{_name_slug(o, n)}@example.com"
    )
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
