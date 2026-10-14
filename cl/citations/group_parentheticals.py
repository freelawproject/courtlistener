"""
This module contains the clustering algorithm for grouping
parentheticals of a case into groups of textually-similar parentheticals.

The basic idea here is that many cases are summarized in parentheticals by other
cases repeatedly in similar or even identical ways. We want to identify and group
those similar parentheticals so that we can (a) not show the user repetitive
information in the limited space we have and (b) identify which ideas are most
often described so that we can rank them higher in the results.

The main outward-facing function is :get_parenthetical_groups, which takes in
a list of Parenthetical objects and returns a list of ComputedParentheticalGroup
objects containing those parentheticals and certain metadata about the groups.

Implementation-wise, we are doing an approximation of Jaccard similarity
(https://en.wikipedia.org/wiki/Jaccard_index) between the tokens of every
parenthetical and every other and group together those parentheticals that
are above a certain threshold of similarity to each other. To do this
efficiently, we make use of the datasketch library's implementation of MinHash,
an algorithm known as a locality-sensitive hashing (LSH) algorithm.

For information about MinHash, here are a couple of good resources:
https://medium.com/@jonathankoren/near-duplicate-detection-b6694e807f7a
https://ekzhu.com/datasketch/lsh.html

A detailed explanation of the implementation and motivation for this algorithm
can be found in the following issue and pull request:
https://github.com/freelawproject/courtlistener/issues/1931
https://github.com/freelawproject/courtlistener/pull/1941
"""

import re
from collections.abc import Callable, Hashable, Iterable
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from math import ceil
from typing import Any, Protocol

from datasketch import MinHash, MinHashLSH
from Stemmer import (  # type:ignore[missing-import] Stemmer has no associated py or pyi file
    Stemmer,
)

from cl.lib.stop_words import STOP_WORDS

GERUND_WORD = re.compile(r"(?:\S+ing)", re.IGNORECASE)

SIMILARITY_THRESHOLD = 0.5

# Initializing the LSH/Minhashes is very slow because it has to generate
# a ton of random numbers. But we can avoid repeating that work
# every time we compute groups by simply using python's deepcopy
# method to clone this reference object. It really seems too stupid
# to work, but it does, perfectly, and gives us a huge speed-up.
_EMPTY_SIMILARITY_INDEX = MinHashLSH(
    threshold=SIMILARITY_THRESHOLD, num_perm=64
)
_EMPTY_MHASH = MinHash(num_perm=64)

# We initialize the stemmer once and reuse it because it internally caches
# frequently seen tokens, giving us a performance benefit if we reuse it.
stemmer = Stemmer("english")


class GroupableParenthetical(Protocol):
    """What grouping reads from a parenthetical.

    A Parenthetical model instance satisfies this, but so does a lighter
    object: callers grouping a heavily cited case should prefer one, since a
    model instance costs ~1.5 KiB and a case can have tens of thousands.
    """

    @property
    def id(self) -> int: ...

    @property
    def text(self) -> str: ...

    @property
    def score(self) -> float: ...


@dataclass
class ComputedParentheticalGroup[P: GroupableParenthetical]:
    # So named to avoid collision with the database model named ParentheticalGroup
    parentheticals: list[P]
    representative: P
    size: int
    score: float


def compute_parenthetical_groups[P: GroupableParenthetical](
    parentheticals: list[P],
) -> list[ComputedParentheticalGroup[P]]:
    """
    Given a list of parentheticals for a case, cluster them based on textual
    similarity and returns a list of ComputedParentheticalGroup objects containing
    these clusters and their metadata.

    For example, imagine that a case makes three important
    points of law, and that those are summarized in 200 parentheticals.
    In that case, what we'd want to do is take those 200 parentheticals
    and identify which of them are basically the same, and then merge
    them into three ComputedParentheticalGroups (one for each point of law).
    From there, we put those in a list and return the list of groups.

    :param parentheticals: A list of parentheticals to organize into groups
    :return: A list of ComputedParentheticalGroup's containing the given parentheticals
    """
    # Clear tokenization cache to avoid cross-request and cross-test contamination.
    # The cache is intended to speed up repeated tokenization within a single
    # clustering invocation, but should not persist across independent runs.
    get_parenthetical_tokens.cache_clear()
    if len(parentheticals) == 0:
        return []

    similarity_index = deepcopy(_EMPTY_SIMILARITY_INDEX)
    parenthetical_objects: dict[int, P] = {}

    for par in parentheticals:
        mhash = deepcopy(_EMPTY_MHASH)
        tokens = get_parenthetical_tokens(par.text)
        mhash.update_batch([gram.encode("utf-8") for gram in tokens])
        parenthetical_objects[par.id] = par
        # The index keeps what grouping needs, so each MinHash can go now.
        similarity_index.insert(par.id, mhash)

    def neighbor_count(par: P) -> int:
        return count_similar(similarity_index, par.id)

    parenthetical_groups = [
        get_group_from_component(
            component, parenthetical_objects, neighbor_count
        )
        for component in connected_components(
            parenthetical_objects, lsh_buckets(similarity_index)
        )
    ]
    return sorted(
        parenthetical_groups, key=lambda group: group.score, reverse=True
    )


def lsh_buckets(similarity_index: MinHashLSH) -> Iterable[Iterable[Any]]:
    """Yield every bucket of an LSH index as a collection of keys.

    Two keys are similar exactly when some bucket holds both: that is the
    relation `MinHashLSH.query` reports, one bucket per band.

    :param similarity_index: A populated MinHashLSH index
    :return: An iterable of buckets, each an iterable of the keys inserted
    """
    for hashtable in similarity_index.hashtables:
        for band_hash in hashtable.keys():
            yield hashtable.get(band_hash)


def connected_components[K: Hashable](
    keys: Iterable[K], buckets: Iterable[Iterable[K]]
) -> list[list[K]]:
    """Group keys that are linked, directly or through others, by buckets.

    Every key in a bucket is linked to every other key in it. This builds the
    same components as walking a graph with an edge between each pair of keys
    that share a bucket, without ever materializing those edges: a cluster of
    n near-identical parentheticals has n² edges, which is what made grouping
    a heavily cited case cost gigabytes.

    :param keys: Every key, in the order components and their members should
        follow
    :param buckets: Collections of keys known to be linked
    :return: The components, ordered by their earliest key; members keep the
        order of `keys`
    """
    parent: dict[K, K] = {key: key for key in keys}

    def find(key: K) -> K:
        root = key
        while parent[root] != root:
            root = parent[root]
        # Point the whole path at the root so later finds are short.
        while parent[key] != root:
            parent[key], key = root, parent[key]
        return root

    for bucket in buckets:
        iterator = iter(bucket)
        if (first := next(iterator, None)) is None:
            continue
        root = find(first)
        for key in iterator:
            if (other := find(key)) != root:
                parent[other] = root

    components: dict[K, list[K]] = {}
    for key in parent:
        components.setdefault(find(key), []).append(key)
    return list(components.values())


def count_similar(similarity_index: MinHashLSH, key: Hashable) -> int:
    """Count the keys similar to `key` in an LSH index, including itself.

    This equals `len(similarity_index.query(...))` for the key's MinHash, but
    works from the band hashes the index already stores, so callers need not
    keep MinHashes around.

    :param similarity_index: A populated MinHashLSH index
    :param key: A key inserted into the index
    :return: The number of keys sharing at least one bucket with `key`
    """
    band_hashes = similarity_index.keys.get(key)
    return len(
        set().union(
            *(
                hashtable.get(band_hash)
                for band_hash, hashtable in zip(
                    band_hashes, similarity_index.hashtables
                )
            )
        )
    )


def get_group_from_component[P: GroupableParenthetical](
    component: list[int],
    parenthetical_objects: dict[int, P],
    neighbor_count: Callable[[P], int],
) -> ComputedParentheticalGroup[P]:
    """
    Given a list of parenthetical IDs representing a component, create a
    ComputedParentheticalGroup containing the corresponding parenthetical objects,
    the most representative parenthetical from among the component, and
    sort the parentheticals by their descriptiveness score.

    :param component: A list of parenthetical IDs to turn into a ComputedParentheticalGroup
    :param parenthetical_objects: A dictionary mapping parenthetical IDs to the
    corresponding parenthetical objects
    :param neighbor_count: Returns how many parentheticals are similar to a
    given one, itself included
    :return: A ComputedParentheticalGroup corresponding to the given component
    """
    pars_in_group = sorted(
        (parenthetical_objects[par_id] for par_id in component),
        key=lambda par: par.score,
        reverse=True,
    )
    # Score of the top-ranked parenthetical times the proportion of
    # total parentheticals in this group
    group_score = pars_in_group[0].score * (
        len(pars_in_group) / len(parenthetical_objects)
    )
    representative = get_representative_parenthetical(
        pars_in_group, neighbor_count
    )
    parenthetical_group = ComputedParentheticalGroup(
        parentheticals=pars_in_group,
        representative=representative,
        size=len(pars_in_group),
        score=group_score,
    )
    return parenthetical_group


BEST_PARENTHETICAL_SEARCH_THRESHOLD = 0.2


def get_representative_parenthetical[P: GroupableParenthetical](
    parentheticals: list[P],
    neighbor_count: Callable[[P], int],
) -> P:
    """
    Takes a list of parentheticals sorted by score and returns the parenthetical
    in the top 20% of score that is most similar to the cluster as a whole
    (as determined by its number of neighbors)

    :param parentheticals: A list of parentheticals sorted by score, descending
    :param neighbor_count: Returns how many parentheticals are similar to a
    given one. Called only for the top 20%, since counting can be costly in
    large groups.
    :return: A Parenthetical object of the best parenthetical in the group
    """
    num_parentheticals_to_consider = ceil(
        len(parentheticals) * BEST_PARENTHETICAL_SEARCH_THRESHOLD
    )
    return max(
        parentheticals[:num_parentheticals_to_consider], key=neighbor_count
    )


# Cache tokenization results to reduce repeated work during clustering,
# which frequently processes many identical or near-identical parentheticals.
# Benchmarks show >99% cache hit rates in realistic workloads, and a ~65×
# speedup in tokenization-heavy paths. A maxsize of 4096 comfortably covers
# repetition within a single clustering invocation while keeping memory bounded.
@lru_cache(maxsize=4096)
def get_parenthetical_tokens(text: str) -> list[str]:
    """
    For a given text string, tokenize it, and filter stop words.

    :param text: The parenthetical text to tokenize
    :return: A list of stemmed and filtered tokens from the provided text
    """
    # Remove non-alphanumeric and non-whitespace characters from text
    cleaned_text = re.sub(r"[^A-Za-z0-9 ]+", "", text).lower()
    # Split text into tokens and remove stop words (e.g. "that", "and", "of")
    tokens = [word for word in cleaned_text.split() if word not in STOP_WORDS]
    # Treat "holding", "recognizing" etc. at first position as a stop word
    if len(tokens) > 0 and GERUND_WORD.match(tokens[0]):
        del tokens[0]
    tokens = stemmer.stemWords(tokens)
    return tokens
