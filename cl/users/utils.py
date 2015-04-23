import hashlib
from cl.users.models import UserProfile
from django.contrib.auth.models import User


def create_stub_account(user_data, profile_data):
    email = user_data['email']
    new_user = User.objects.create_user(
        # Username can only be 30 chars long. Use a hash of the
        # email address to reduce the odds of somebody
        # wanting to create an account that already exists.
        # We'll change this to good values later, when the stub
        # account is upgraded to a real account with a real
        # username.
        hashlib.md5(email).hexdigest()[:30],
        email,
    )
    new_user.first_name = user_data['first_name']
    new_user.last_name = user_data['last_name']

    # Associate a profile
    profile = UserProfile(
        user=new_user,
        stub_account=True,
        address1=profile_data['address1'],
        address2=profile_data.get('address2'),
        city=profile_data['city'],
        state=profile_data['state'],
        zip_code=profile_data['zip_code'],
        wants_newsletter=profile_data['wants_newsletter']
    )
    return new_user, profile

def convert_to_stub_account(user):
    """ Set all fields to as blank as possible.

    :param user: The user to operate on.
    :return: The new user object.
    """
    user.first_name = None
    user.last_name = None
    user.username = hashlib.md5(user.email).hexdigest()[:30]
    user.set_unusable_password()
    user.save()

    profile = user.profile
    profile.address1 = None
    profile.address2 = None
    profile.barmembership = []
    profile.city = None
    profile.employer = None
    profile.state = None
    profile.stub_account = True
    profile.wants_newsletter = False
    profile.zip_code = None
    profile.save()

    return user




