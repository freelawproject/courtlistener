import hashlib


def sha1(s):
    """Return the sha1 of a string as a hex digest."""
    sha1sum = hashlib.sha256()
    sha1sum.update(s)
    return sha1sum.hexdigest()
