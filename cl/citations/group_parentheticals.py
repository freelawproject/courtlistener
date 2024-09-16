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
from copy import deepcopy
from dataclasses import dataclass
from math import ceil
from typing import Dict, List, Set

from datasketch import MinHash, MinHashLSH
from Stemmer import Stemmer

from cl.lib.stop_words import STOP_WORDS
from cl.search.models import Parenthetical

Graph = Dict[str, List[str]]

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


@dataclass
class ComputedParentheticalGroup:
    # So named to avoid collision with the database model named ParentheticalGroup
    parentheticals: List[Parenthetical]
    representative: Parenthetical
    size: int
    score: float


def compute_parenthetical_groups(
    parentheticals: List[Parenthetical],
) -> List[ComputedParentheticalGroup]:
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
    if len(parentheticals) == 0:
        return []

    similarity_index = deepcopy(_EMPTY_SIMILARITY_INDEX)
    parenthetical_objects: Dict[str, Parenthetical] = {}
    parenthetical_minhashes: Dict[str, MinHash] = {}

    for par in parentheticals:
        mhash = deepcopy(_EMPTY_MHASH)
        tokens = get_parenthetical_tokens(par.text)
        mhash.update_batch([gram.encode("utf-8") for gram in tokens])

        par_key = str(par.id)
        parenthetical_objects[par_key] = par
        parenthetical_minhashes[par_key] = mhash
        similarity_index.insert(par_key, mhash)

    similarity_graph = get_similarity_graph(
        parenthetical_minhashes, similarity_index
    )

    parenthetical_groups: List[ComputedParentheticalGroup] = []
    visited_nodes: Set[str] = set()
    for node, neighbors in similarity_graph.items():
        if component := get_graph_component(
            node, similarity_graph, visited_nodes
        ):
            parenthetical_groups.append(
                get_group_from_component(
                    component,
                    parenthetical_objects,
                    similarity_graph,
                )
            )
    return sorted(
        parenthetical_groups, key=lambda group: group.score, reverse=True
    )


def get_similarity_graph(
    parenthetical_minhashes: Dict[str, MinHash], similarity_index: MinHashLSH
) -> Graph:
    """
    From the MinHashLSH index, create a dictionary representation of a graph
    where the nodes represent parentheticals and the edges represent that
    two nodes are sufficiently similar to each other to be clustered into
    the same group.

    :param parenthetical_minhashes: A dictionary mapping parenthetical IDs to
    the MinHash object corresponding to the parenthetical's text's tokens
    :param similarity_index: The MinHashLSH data structure containing all of
    the MinHash's that we can query
    :return: A dictionary representation of a graph/network where the nodes/keys
    are parenthetical IDs and the neighbors/values are the other parentheticals
    above the defined similarity threshold.
    """
    similarity_graph: Graph = {}
    for par_key, mhash in parenthetical_minhashes.items():
        similarity_graph[par_key] = similarity_index.query(mhash)
    return similarity_graph


def get_graph_component(
    node: str, graph: Graph, visited: Set[str]
) -> List[str]:
    """
    From a given starting node, find the list of nodes connected to it either
    directly or indirectly. In graph theory terms, this is a "connected
    component": https://www.geeksforgeeks.org/connected-components-in-an-undirected-graph/

    :param node: The starting node from which to probe the component
    :param graph: A dictionary encoding the graph with key: node and value:
    list of neighbors
    :param visited: A set containing the nodes already visited in the DFS
    :return: A list of all nodes in param :node's component
    """
    current_cluster = []
    # Perform a depth-first search to find all nodes in the component
    if node not in visited:
        visited.add(node)
        current_cluster.append(node)
        for neighbor in graph[node]:
            current_cluster.extend(
                get_graph_component(neighbor, graph, visited)
            )
    return current_cluster


def get_group_from_component(
    component: List[str],
    parenthetical_objects: Dict[str, Parenthetical],
    similarity_graph: Graph,
) -> ComputedParentheticalGroup:
    """
    Given a list of parenthetical IDs representing a component, create a
    ComputedParentheticalGroup containing the corresponding parenthetical objects,
    the most representative parenthetical from among the component, and
    sort the parentheticals by their descriptiveness score.

    :param component: A list of parenthetical IDs to turn into a ComputedParentheticalGroup
    :param parenthetical_objects: A dictionary mapping parenthetical IDs to the
    corresponding parenthetical objects
    :param similarity_graph: A dictionary containing similarity relationships
    between parentheticals
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
        pars_in_group, similarity_graph
    )
    parenthetical_group = ComputedParentheticalGroup(
        parentheticals=pars_in_group,
        representative=representative,
        size=len(pars_in_group),
        score=group_score,
    )
    return parenthetical_group


BEST_PARENTHETICAL_SEARCH_THRESHOLD = 0.2


def get_representative_parenthetical(
    parentheticals: List[Parenthetical], similarity_graph: Graph
) -> Parenthetical:
    """
    Takes a list of parentheticals sorted by score and returns the parenthetical
    in the top 20% of score that is most similar to the cluster as a whole
    (as determined by its number of neighbors)

    :param parentheticals: A list of parentheticals sorted by score, descending
    :param similarity_graph: A dictionary encoding the graph with key: node and value:
    list of neighbors
    :return: A Parenthetical object of the best parenthetical in the group
    """
    num_parentheticals_to_consider = ceil(
        len(parentheticals) * BEST_PARENTHETICAL_SEARCH_THRESHOLD
    )
    return max(
        parentheticals[:num_parentheticals_to_consider],
        # The number of neighbors each parenthetical has
        key=lambda par: len(similarity_graph[str(par.id)]),
    )


def get_parenthetical_tokens(text: str) -> List[str]:
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
