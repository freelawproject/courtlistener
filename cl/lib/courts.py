from dataclasses import dataclass

from django.core.cache import cache

from cl.search.models import Court


def get_cache_key_for_court_list() -> str:
    """
    Retrieves the cache key used to store the list of courts.

    This function provides a consistent and easily identifiable key for caching
    court data. It's particularly useful for:

    -   Ensuring consistent cache access across different parts of the
        application.
    -   Facilitating cache isolation during testing, allowing for predictable
        and controlled test environments.
    -   Simplifying cache invalidation and management.

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
    Retrieves a list of courts with minimal data.

    This method fetches a list of courts from the database, including only the
    primary key (pk), short name, in_use status, jurisdiction, and parent court
    ID. It uses a cache to store and retrieve this data, reducing db load.

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

    This method fetches the court data using `get_minimal_list_of_courts()`. it
    then filters this list to include only courts where the 'in_use' attribute
    is True.

    :returns: A list of MinimalCourtData objects representing active courts.
    """
    courts = get_minimal_list_of_courts()
    return [c for c in courts if c.in_use]


def get_parent_ids_from_cache(courts: list[MinimalCourtData]) -> set[str]:
    """
    Extracts the unique parent court IDs from a list of court objects.

    :returns: A set containing the unique parent court IDs, excluding None
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

    Returns:
        A set containing the original court IDs and all their descendant court
        IDs.
    """
    if not court_ids:
        return set()

    courts_from_cache = get_minimal_list_of_courts()
    parent_court_ids = get_parent_ids_from_cache(courts_from_cache)
    courts = set(court_ids)

    # check if the input has at least a child
    if courts.isdisjoint(parent_court_ids):
        # If none of the input court IDs are parent court IDs, there are no
        # children.
        return set()

    child_courts: set[str] = set()
    # step will hold the child courts found in the previous iteration.
    step: set[str] = set()
    while True:
        # In the first iteration, use the original courts, then use the courts
        # found in the previous step. create the set of child court ids from
        # memory
        courts_to_check = step or courts

        # create the set of child court ids from memory
        new_child = {
            court.pk
            for court in courts_from_cache
            if court.parent_court_id in courts_to_check
        }

        # Update the set of child courts found so far.
        child_courts.update(new_child)
        if new_child.isdisjoint(parent_court_ids):
            # If no new children are parent courts, then stop iterating, as
            # there are no more levels.
            break
        step = new_child

    # Add all the found ids to the original set of courts.
    courts.update(child_courts)
    return courts
