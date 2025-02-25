from typing import Any

from django.forms.models import model_to_dict

from cl.recap.models import PacerFetchQueue
from cl.search.models import Docket


def get_court_id_from_fetch_queue(fq: PacerFetchQueue | dict[str, Any]) -> str:
    """Extracts the court ID from a PacerFetchQueue object or a dictionary.

    This function attempts to retrieve the court ID from the provided
    PacerFetchQueue object or dictionary. It checks for the court ID in
    the following order:

    1. From the recap_document's docket_entry's docket.
    2. From the docket object.
    3. The top-level `court_id` (for PacerFetchQueue objects) or `court.pk`
       (for dictionaries).

    :param fq: A PacerFetchQueue object or a dictionary representing a
    PacerFetchQueue.
    :return: The court ID as a string.
    """
    # Check if the input is a PacerFetchQueue object or a dictionary.
    is_fetch_queue = isinstance(fq, PacerFetchQueue)

    # Convert PacerFetchQueue to dictionary if necessary.  This allows us to
    # handle both types consistently.
    attrs = model_to_dict(fq) if is_fetch_queue else fq

    if attrs.get("recap_document"):
        rd_id = (
            fq.recap_document_id
            if is_fetch_queue
            else attrs["recap_document"].pk
        )
        docket = (
            Docket.objects.filter(docket_entries__recap_documents__id=rd_id)
            .only("court_id")
            .first()
        )
        court_id = docket.court_id
    elif attrs.get("docket"):
        court_id = (
            fq.docket.court_id if is_fetch_queue else attrs["docket"].court_id
        )
    else:
        court_id = fq.court_id if is_fetch_queue else attrs["court"].pk

    return court_id
