"""The loaders a state scrape run can be loaded with, by name.

A load dispatches its merges to celery, so the worker that picks one up has to
find its way back to the loader that sent it. It must not be handed an
importable path, which would let anything on the queue name any callable in
the codebase. It is handed a name out of this registry instead, which can only
name what is registered here.

Register a court by adding its `JKentScrapeLoader` subclass here. The name a
loader is registered under is its own `name`, so the two cannot drift apart.
"""

from typing import Any

from cl.corpus_importer.state.loader import JKentScrapeLoader
from cl.corpus_importer.state.new_york.loader import NYCoACourtPassLoader

LOADERS: dict[str, type[JKentScrapeLoader[Any, Any]]] = {
    loader.name: loader for loader in (NYCoACourtPassLoader,)
}


def get_loader(name: str) -> type[JKentScrapeLoader[Any, Any]]:
    """The loader registered under `name`.

    :param name: A key of `LOADERS`.
    :return: The loader class.
    :raises KeyError: If nothing is registered under `name`. A merge task
        given an unknown name has been sent something it cannot merge, and
        retrying it will not help.
    """
    return LOADERS[name]
