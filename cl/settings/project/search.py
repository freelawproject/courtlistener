import os

import environ

env = environ.FileAwareEnv()

SOLR_HOST = env("SOLR_HOST", default="http://cl-solr:8983")
SOLR_RECAP_HOST = env("SOLR_RECAP_HOST", default="http://cl-solr:8983")
SOLR_PAGERANK_DEST_DIR = env("SOLR_PAGERANK_DEST_DIR", default="/tmp/")

########
# Solr #
########
SOLR_OPINION_URL = f"{SOLR_HOST}/solr/collection1"
SOLR_AUDIO_URL = f"{SOLR_HOST}/solr/audio"
SOLR_PEOPLE_URL = f"{SOLR_HOST}/solr/person"
SOLR_RECAP_URL = f"{SOLR_RECAP_HOST}/solr/recap"
SOLR_URLS = {
    "audio.Audio": SOLR_AUDIO_URL,
    "people_db.Person": SOLR_PEOPLE_URL,
    "search.Docket": SOLR_RECAP_URL,
    "search.RECAPDocument": SOLR_RECAP_URL,
    "search.Opinion": SOLR_OPINION_URL,
    "search.OpinionCluster": SOLR_OPINION_URL,
}

SOLR_OPINION_TEST_CORE_NAME = "opinion_test"
SOLR_AUDIO_TEST_CORE_NAME = "audio_test"
SOLR_PEOPLE_TEST_CORE_NAME = "person_test"
SOLR_RECAP_TEST_CORE_NAME = "recap_test"

SOLR_OPINION_TEST_URL = f"{SOLR_HOST}/solr/opinion_test"
SOLR_AUDIO_TEST_URL = f"{SOLR_HOST}/solr/audio_test"
SOLR_PEOPLE_TEST_URL = f"{SOLR_HOST}/solr/person_test"
SOLR_RECAP_TEST_URL = f"{SOLR_RECAP_HOST}/solr/recap_test"
SOLR_TEST_URLS = {
    "audio.Audio": SOLR_AUDIO_TEST_URL,
    "people_db.Person": SOLR_PEOPLE_TEST_URL,
    "search.Docket": SOLR_RECAP_TEST_URL,
    "search.RECAPDocument": SOLR_RECAP_TEST_URL,
    "search.Opinion": SOLR_OPINION_TEST_URL,
    "search.OpinionCluster": SOLR_OPINION_TEST_URL,
}
SOLR_EXAMPLE_CORE_PATH = os.path.join(
    os.sep, "usr", "local", "solr", "example", "solr", "collection1"
)
SOLR_TEMP_CORE_PATH_LOCAL = os.path.join(os.sep, "tmp", "solr")
SOLR_TEMP_CORE_PATH_DOCKER = os.path.join(os.sep, "tmp", "solr")


###################
# Related content #
###################
RELATED_COUNT = 5
RELATED_USE_CACHE = True
RELATED_CACHE_TIMEOUT = 60 * 60 * 24 * 7
RELATED_MLT_MAXQT = 10
RELATED_MLT_MINTF = 5
RELATED_MLT_MAXDF = 1000
RELATED_MLT_MINWL = 3
RELATED_MLT_MAXWL = 0
RELATED_FILTER_BY_STATUS = "Precedential"
QUERY_RESULTS_CACHE = 60 * 60 * 6

#####################
# Search pagination #
#####################
MAX_SEARCH_PAGINATION_DEPTH = 100
SEARCH_PAGE_SIZE = 20
CHILD_HITS_PER_RESULT = 5
VIEW_MORE_CHILD_HITS = 99
# The amount of text to return from the beginning of the field if there are no
# matching fragments to highlight.
NO_MATCH_HL_SIZE = 500
