from dataclasses import dataclass

from django.core.cache import cache

from cl.search.models import Court


def get_cache_key_for_court_list() -> str:
    """
    Returns the cache key used to store the list of courts. This method
    allows predictable cache isolation during testing.

    :return: The cache key, which is currently "minimal-court-list".
    """
    return "minimal-court-list"


@dataclass
class MinimalCourtData:
    pk: str
    short_name: str
    in_use: bool
    parent_court_id: str | None


def get_minimal_list_of_courts() -> list[MinimalCourtData]:
    """
    Retrieves a list of courts with essential information.

    It uses a cache to store and retrieve this data, reducing db load.

    The cache is set to expire after 24 hours.

    :return: A list of MinimalCourtData objects
    """

    data = cache.get(get_cache_key_for_court_list())
    if data is not None:
        return data

    courts = list(
        Court.objects.values("pk", "short_name", "in_use", "parent_court_id")
    )
    court_list = [MinimalCourtData(**court) for court in courts]
    cache.set(get_cache_key_for_court_list(), court_list, 60 * 60 * 24)

    return court_list


def get_active_court_from_cache() -> list[MinimalCourtData]:
    """
    Retrieves a list of active courts from the cached court data.

    :return: A list of MinimalCourtData objects representing active courts.
    """
    courts = get_minimal_list_of_courts()
    return [c for c in courts if c.in_use]


def get_court_parent_ids(courts: list[MinimalCourtData]) -> set[str]:
    """
    Extracts the unique parent court IDs from a list of court objects.

    :return: A set containing the unique parent court IDs, excluding None
        values.
    """
    court_ids = {
        court.parent_court_id for court in courts if court.parent_court_id
    }
    return court_ids


def lookup_child_courts_cache(court_ids: list[str]) -> set[str]:
    """
    Recursively finds all child court IDs for a given list of court IDs, using
    a cached list of courts.

    :return: A set containing the original court IDs and all their descendant
        court IDs.
    """
    if not court_ids:
        return set()

    courts_from_cache = get_minimal_list_of_courts()
    parent_court_ids = get_court_parent_ids(courts_from_cache)
    courts = set(court_ids)

    # check if the input has at least a child
    if courts.isdisjoint(parent_court_ids):
        # If none of the input court IDs are parent court IDs, there are no
        # children.
        return set()

    # step will hold the child courts found in the previous iteration.
    # In the first iteration, use the original courts, then use the courts
    # found in the previous step. create the set of child court ids from
    # memory
    step: set[str] = courts
    while True:
        # create the set of child court ids from memory
        new_child = {
            court.pk
            for court in courts_from_cache
            if court.parent_court_id in step
        }

        # Only consider IDs we haven't seen before to avoid infinite loops due
        # to courts pointing to themselves.
        new_ids = new_child - courts
        if not new_ids:
            break

        # Update the set of child courts found so far.
        courts.update(new_ids)
        if new_ids.isdisjoint(parent_court_ids):
            # If no new children are parent courts, then stop iterating, as
            # there are no more levels.
            break
        step = new_ids

    return courts
