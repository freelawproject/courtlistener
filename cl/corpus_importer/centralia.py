# Code for importing Centralia structured opinion extractions into the DB
from cl.search.models import Opinion

# Centralia's opinion kind -> CL opinion type.
# CL has no per-curiam type, so per curiam opinions are stored as
# lead opinions with the per_curiam flag set. Kinds missing here, such as
# "order", fall back to lead in map_centralia_opinion_type.
CENTRALIA_OPINION_TYPES: dict[str, str] = {
    "majority": Opinion.LEAD,
    "per-curiam": Opinion.LEAD,
    "concurrence": Opinion.CONCURRENCE,
    "concurrence-in-result": Opinion.CONCURRENCE,
    "concurring-in-part-and-dissenting-in-part": Opinion.CONCUR_IN_PART,
    "dissent": Opinion.DISSENT,
    "addendum": Opinion.ADDENDUM,
    "rehearing": Opinion.REHEARING,
}


def normalize_centralia_opinion_type(centralia_type: str | None) -> str:
    """Normalize a Centralia opinion type for lookups and comparisons.

    :param centralia_type: The `opinions[].type` value returned by Centralia.
    :return: The type, stripped and lowercased; "" when missing.
    """
    return (centralia_type or "").strip().lower()


def map_centralia_opinion_type(centralia_type: str | None) -> str:
    """Map a Centralia opinion type to a CL opinion type.

    Combined is deliberately never returned. It means an import could not
    tell one writing from another, and Centralia's whole purpose is to say
    how many writings a document holds and where each begins, so a lone
    writing is the lead opinion, not a combined one. Unrecognized types,
    including "order", are also lead: a paper Centralia cannot name is
    likelier to be the decision itself than a concurrence or dissent, both
    of which it names.

    :param centralia_type: The `opinions[].type` value returned by Centralia.
    :return: The CL opinion type.
    """
    return CENTRALIA_OPINION_TYPES.get(
        normalize_centralia_opinion_type(centralia_type), Opinion.LEAD
    )
