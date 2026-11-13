from collections.abc import Callable

type Strategy[Scrape, Existing, Output = Scrape | Existing] = Callable[
    [Scrape, Existing], Output
]


def overwrite[T](scrape: T | None, db: T | None) -> T | None:
    """Merge strategy that always overwrites the existing value with the scraped value."""
    return scrape


def overwrite_if_present[T](scrape: T | None, db: T | None) -> T | None:
    """Merge strategy that overwrites the existing value only when the scraped value is present (i.e. not `None`), otherwise keeping the DB value."""
    return db if scrape is None else scrape
