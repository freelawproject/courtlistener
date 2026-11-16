"""Choices for where oral argument audio came from."""


class AudioSources:
    """Where an oral argument audio file came from."""

    COURT_WEBSITE = "C"
    BRAD_HEATH_ARCHIVE = "H"

    NAMES = (
        (COURT_WEBSITE, "court website"),
        (BRAD_HEATH_ARCHIVE, "brad heath archive"),
    )
