import os

import environ

env = environ.FileAwareEnv()

###################
# Export setting #
###################
MAX_SEARCH_RESULTS_EXPORTED = env("MAX_SEARCH_RESULTS_EXPORTED", default=250)

###################
# Related content #
###################
RELATED_COUNT = 20
RELATED_USE_CACHE = True
RELATED_CACHE_TIMEOUT = 60 * 60 * 24 * 7
RELATED_MLT_MAXQT = 10
RELATED_MLT_MINTF = 5
RELATED_MLT_MAXDF = 1000
RELATED_MLT_MINWL = 3
RELATED_MLT_MAXWL = 0
RELATED_FILTER_BY_STATUS = "Precedential"
QUERY_RESULTS_CACHE = 60 * 60 * 6
SEARCH_RESULTS_MICRO_CACHE = 60 * 10

#####################
# Search pagination #
#####################
MAX_SEARCH_PAGINATION_DEPTH = 100
SEARCH_PAGE_SIZE = 20
RECAP_SEARCH_PAGE_SIZE = 10
RECAP_CHILD_HITS_PER_RESULT = env("RECAP_CHILD_HITS_PER_RESULT", default=3)
OPINION_HITS_PER_RESULT = 20
PEOPLE_HITS_PER_RESULT = 999
VIEW_MORE_CHILD_HITS = 99
SEARCH_API_PAGE_SIZE = 20
# The amount of text to return from the beginning of the field if there are no
# matching fragments to highlight.
NO_MATCH_HL_SIZE = 500


###################
# SEMANTIC SEARCH #
###################
MIN_OPINION_SIZE = env("MIN_OPINION_SIZE", default=100)
NLP_EMBEDDING_MODEL = env(
    "NLP_EMBEDDING_MODEL_NAME",
    default="freelawproject/modernbert-embed-base_finetune_512",
)
