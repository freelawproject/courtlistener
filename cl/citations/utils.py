from cl.search.models import Citation


def map_reporter_db_cite_type(citation_type):
    """Map a citation type from the reporters DB to CL Citation type

    :param citation_type: A value from REPORTERS['some-key']['cite_type']
    :return: A value from the search.models.Citation object
    """
    if citation_type == "specialty":
        model_citation_type = Citation.SPECIALTY
    elif citation_type == "federal":
        model_citation_type = Citation.FEDERAL
    elif citation_type == "state":
        model_citation_type = Citation.STATE
    elif citation_type == "state_regional":
        model_citation_type = Citation.STATE_REGIONAL
    elif citation_type == "neutral":
        model_citation_type = Citation.NEUTRAL
    elif citation_type == "lexis":
        model_citation_type = Citation.LEXIS
    elif citation_type == "west":
        model_citation_type = Citation.WEST
    elif citation_type == "scotus_early":
        model_citation_type = Citation.SCOTUS_EARLY
    else:
        model_citation_type = None
