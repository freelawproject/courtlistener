from django.urls.converters import StringConverter


class BlankSlugConverter(StringConverter):
    """A slug converter that allows blank values

    This just swapped out the plus sign in the SlugConverter for an asterisk.
    """

    regex = "[-a-zA-Z0-9_]*"
