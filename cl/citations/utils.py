from lxml import etree

from django.db.models import Sum
from django.apps import (
    apps,
)  # Must use apps.get_model() to avoid circular import issue


def map_reporter_db_cite_type(citation_type):
    """Map a citation type from the reporters DB to CL Citation type

    :param citation_type: A value from REPORTERS['some-key']['cite_type']
    :return: A value from the search.models.Citation object
    """
    Citation = apps.get_model("search.Citation")
    citation_map = {
        "specialty": Citation.SPECIALTY,
        "federal": Citation.FEDERAL,
        "state": Citation.STATE,
        "state_regional": Citation.STATE_REGIONAL,
        "neutral": Citation.NEUTRAL,
        "specialty_lexis": Citation.LEXIS,
        "specialty_west": Citation.WEST,
        "scotus_early": Citation.SCOTUS_EARLY,
    }
    return citation_map.get(citation_type)


def get_citation_depth_between_clusters(citing_cluster_pk, cited_cluster_pk):
    """OpinionsCited objects exist as relationships between Opinion objects,
    but we often want access to citation depth information between
    OpinionCluster objects. This helper method assists in doing the necessary
    DB lookup.

    :param citing_cluster_pk: The primary key of the citing OpinionCluster
    :param cited_cluster_pk: The primary key of the cited OpinionCluster
    :return: The sum of all the depth fields of the OpinionsCited objects
        associated with the Opinion objects associated with the given
        OpinionCited objects
    """
    OpinionsCited = apps.get_model("search.OpinionsCited")
    return OpinionsCited.objects.filter(
        citing_opinion__cluster__pk=citing_cluster_pk,
        cited_opinion__cluster__pk=cited_cluster_pk,
    ).aggregate(depth=Sum("depth"))["depth"]


def is_balanced_html(text):
    """Test whether a given string contains balanced HTML tags

    :param text: The string to be tested
    :return: Boolean
    """
    text = "<div>%s</div>" % text

    # lxml will throw an error while parsing if the string is unbalanced
    try:
        etree.fromstring(text)
        return True
    except:
        return False
