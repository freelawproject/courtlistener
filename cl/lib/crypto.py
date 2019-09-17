import hashlib
import json
import random
import uuid


def sha1(s):
    """Return the sha1sum of a string.

    :param s: The data to hash
    :return: a hexadecimal SHA1 hash of the data
    """
    sha1sum = hashlib.sha1()
    sha1sum.update(s)
    return sha1sum.hexdigest()


def sha1_of_file(file_path, buffer_size=2**16):
    """Generate a SHA1 hash of a file in constant memory

    :param file_path: The path to the file to hash.
    :param buffer_size: The amount of data to read into memory at a time,
    default is 64Kb.
    :return: A hexadecimal SHA1 hash of the file.
    """
    sha1sum = hashlib.sha1()
    with open(file_path, 'rb') as f:
        while True:
            data = f.read(buffer_size)
            if not data:
                break
            sha1sum.update(data)
    return sha1sum.hexdigest()


def sha1_of_json_data(d):
    """
    Generate SHA1 from case_data, stripping whitespace

    :param d: LASC Search Object
    :return: A generated SHA1 code.
    """
    json_as_python = json.loads(d)
    json_without_spaces = json.dumps(json_as_python, separators=(',', ':'))
    return sha1(json_without_spaces)


def sha1_activation_key(s):
    """Make an activation key for a user

    :param s: The data to use with the salt to make the activation key
    :return: A SHA1 activation key
    """
    salt = hashlib.sha1(str(random.random())).hexdigest()[:5]
    activation_key = hashlib.sha1(salt + s).hexdigest()
    return activation_key


def sha256(s):
    """Return the sha256sum of a string.

    :param s: The data to hash
    :return A hexidecimal SHA256 hash of the data
    """
    sha256sum = hashlib.sha256()
    sha256sum.update(s)
    return sha256sum.hexdigest()


def uuid_hex():
    """Generate a UUID4 hex code

    :return: A UUID4 hex code
    """
    return uuid.uuid4().hex
