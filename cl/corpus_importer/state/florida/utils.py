# Non-comprehensive list of court IDs that can be handled by Florida make_docket_number_core
FLORIDA_COURT_IDS: set[str] = {
    "fl",
    "fladistctapp",
    "fladistctapp1",
    "fladistctapp2",
    "fladistctapp3",
    "fladistctapp4",
    "fladistctapp5",
    "fladistctapp6",
}


def is_florida_court(court_id: str) -> bool:
    """Check if the given `court_id` belongs to a Florida state court.

    :param court_id: The court ID to check.
    :return: Whether the ID belongs to a Florida state court."""

    return court_id in FLORIDA_COURT_IDS


def make_docket_number_core(
    docket_number: str, /, court_id: str = "fl"
) -> str:
    """Normalize Florida docket numbers.

    The `court_id` parameter helps determine what format to force.

    :param docket_number: The docket number to normalize.
    :param court_id: The court ID of the docket. Defaults to the Supreme Court.
    :return: The normalized Florida docket number."""
    # TODO
    raise NotImplementedError
