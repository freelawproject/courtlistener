import re
from math import log

from cl.search.models import OpinionCluster

_GERUND = re.compile(r"(?:\S+ing)", re.IGNORECASE)
_GERUND_THAT = re.compile(rf"{_GERUND.pattern} that", re.IGNORECASE)
_HOLDING = re.compile(
    r"(?:holding|deciding|ruling|recognizing|concluding)", re.IGNORECASE
)
_HOLDING_THAT = re.compile(rf"{_HOLDING.pattern} that", re.IGNORECASE)

# Observation of thousands of parentheticals seems to indicate that the
# most useful ones are in the neighborhood of 20 words long.
# This is completely arbitrary but seems to work pretty well in practice.
OPTIMAL_NUM_WORDS = 20
# We only penalize parentheticals if they are at least this many words away
# from the optimal length.
ALLOWED_NUM_WORDS_DEVIATION = 5
# This is the minimum number of words which suggests that a gerund-starting
# parenthetical is descriptive. Gerund parentheticals are often descriptive
# but are dramatically less likely to be so if they are also short,
# e.g. "relying on common law" and such. When they are more than ~10 words,
# they are as likely to be descriptive as gerunds without 'that'
MINIMUM_WORDS_DESCRIPTIVE = 10


def parenthetical_score(
    description: str, citing_opinion_cluster: OpinionCluster
) -> float:
    """
    Takes a cleaned, non-spam description; returns a usefulness score between 0 and 1.
    """
    num_words = len(description.split(" "))
    # Baseline 500 so we don't end up with negative score when we penalize
    score = 500.0
    # "*ing that..." is the absolute gold standard
    if re.match(_HOLDING_THAT, description):
        score += 400
    elif re.match(_GERUND_THAT, description):
        score += 300
    elif re.match(_HOLDING, description):
        score += 300
    # in general gerunds are nice, but are often not descriptive if they're
    # too short
    elif (
        re.match(_GERUND, description)
        and num_words > MINIMUM_WORDS_DESCRIPTIVE
    ):
        score += 200

    # Reward based on how popular the authoring case is
    # (max of ~125 for the most cited case)
    score += 25 * log(citing_opinion_cluster.citation_count or 1, 10)

    # Penalize if parentheticals are too long or too short
    if num_words < OPTIMAL_NUM_WORDS - ALLOWED_NUM_WORDS_DEVIATION:
        # Major penalty for short parentheticals
        # (max ~ -324 for a 2-word parenthetical)
        score -= (OPTIMAL_NUM_WORDS - num_words) ** 2
    elif num_words > OPTIMAL_NUM_WORDS + ALLOWED_NUM_WORDS_DEVIATION:
        # Minor penalty for long parentheticals
        # (max technically unbounded, but ~ -90 for a 40-word parenthetical)
        score -= (num_words - OPTIMAL_NUM_WORDS) ** 1.5

    # We now have a number approximately between 0 and 1000, scale it down to
    # approximately between 0 and 1
    normalized_score = score / 1000
    # Now cap the score between 0 and 1
    normalized_score = min(max(normalized_score, 0.0), 1.0)
    return normalized_score
