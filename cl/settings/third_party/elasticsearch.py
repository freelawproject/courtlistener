import environ

from ..django import TESTING

env = environ.FileAwareEnv()

if TESTING:
    ELASTICSEARCH_DISABLED = True
    ELASTICSEARCH_RECAP_DOCS_SIGNALS_DISABLED = False
    ELASTICSEARCH_DOCKETS_SIGNALS_DISABLED = False
    ELASTICSEARCH_CLUSTERS_SIGNALS_ENABLED = True
    ELASTICSEARCH_OPINIONS_SIGNALS_ENABLED = True
    ES_HIGHLIGHTER = "fvh"
else:
    ELASTICSEARCH_DISABLED = env(
        "ELASTICSEARCH_DISABLED",
        default=False,
    )
    ELASTICSEARCH_RECAP_DOCS_SIGNALS_DISABLED = env(
        "ELASTICSEARCH_RECAP_DOCS_SIGNALS_DISABLED",
        default=False,
    )
    ELASTICSEARCH_DOCKETS_SIGNALS_DISABLED = env(
        "ELASTICSEARCH_DOCKETS_SIGNALS_DISABLED",
        default=False,
    )
    ELASTICSEARCH_CLUSTERS_SIGNALS_ENABLED = env(
        "ELASTICSEARCH_CLUSTERS_SIGNALS_ENABLED",
        default=True,
    )
    ELASTICSEARCH_OPINIONS_SIGNALS_ENABLED = env(
        "ELASTICSEARCH_OPINIONS_SIGNALS_ENABLED",
        default=True,
    )
    ES_HIGHLIGHTER = env(
        "ES_HIGHLIGHTER",
        default="fvh",
    )
#
# Connection settings
#
ELASTICSEARCH_DSL_HOST = env(
    "ELASTICSEARCH_DSL_HOST",
    default=[
        "https://cl-es:9200",
    ],
)
ELASTICSEARCH_USER = env(
    "ELASTICSEARCH_USER",
    default="elastic",
)
ELASTICSEARCH_PASSWORD = env(
    "ELASTICSEARCH_PASSWORD",
    default="password",
)
ELASTICSEARCH_CA_CERT = env(
    "ELASTICSEARCH_CA_CERT",
    default="/opt/courtlistener/docker/elastic/ca.crt",
)
ELASTICSEARCH_TIMEOUT = env("ELASTICSEARCH_TIMEOUT", default=3500)
ELASTICSEARCH_FAST_QUERIES_TIMEOUT = env(
    "ELASTICSEARCH_FAST_QUERIES_TIMEOUT", default=2
)
base_connection_params = {
    "hosts": ELASTICSEARCH_DSL_HOST,
    "http_auth": (ELASTICSEARCH_USER, ELASTICSEARCH_PASSWORD),
    "verify_certs": False,
    "ca_certs": ELASTICSEARCH_CA_CERT,
    "timeout": ELASTICSEARCH_TIMEOUT,
}
no_retry_conn = base_connection_params.copy()
no_retry_conn["max_retries"] = 0

ELASTICSEARCH_DSL = {
    "default": base_connection_params,
    "no_retry_connection": no_retry_conn,
    "analysis": {
        "analyzer": {
            "text_en_splitting_cl": {
                "type": "custom",
                "tokenizer": "whitespace",
                "filter": [
                    "lowercase",
                    "custom_word_delimiter_filter",
                    "remove_leading_zeros",
                    "english_stop",
                    "english_stemmer",
                    "remove_duplicates",
                ],
            },
            "search_analyzer": {
                "type": "custom",
                "tokenizer": "whitespace",
                "filter": [
                    "lowercase",
                    "synonym_filter",
                    "custom_word_delimiter_filter",
                    "remove_leading_zeros",
                    "english_stop",
                    "english_stemmer",
                    "remove_duplicates",
                ],
            },
            "search_analyzer_exact": {
                "type": "custom",
                "tokenizer": "whitespace",
                "filter": [
                    "lowercase",
                    "custom_word_delimiter_filter",
                    "remove_leading_zeros",
                    "english_stop",
                ],
            },
            "english_exact": {
                "type": "custom",
                "tokenizer": "whitespace",
                "filter": [
                    "lowercase",
                    "custom_word_delimiter_filter",
                    "remove_leading_zeros",
                    "english_stop",
                ],
            },
        },
        "filter": {
            "custom_word_delimiter_filter": {
                "type": "word_delimiter",
                "type_table": [
                    "§ => ALPHANUM",
                    "$ => ALPHANUM",
                    "% => ALPHANUM",
                    "¶ => ALPHANUM",
                ],
                "split_on_numerics": False,
                "preserve_original": True,
            },
            "synonym_filter": {
                "type": "synonym_graph",
                "expand": True,
                "synonyms_path": "dictionaries/synonyms_en.txt",
            },
            "english_stemmer": {"type": "stemmer", "language": "english"},
            "english_stop": {
                "type": "stop",
                "stopwords_path": "dictionaries/stopwords_en.txt",
            },
            "remove_duplicates": {"type": "unique"},
            "remove_leading_zeros": {
                "type": "pattern_replace",
                "pattern": "^0*",
                "replacement": "",
            },
        },
    },
}

#
# Scaling/availability settings
#

# Parenthetical Search index shards and replicas
ELASTICSEARCH_NUMBER_OF_SHARDS = env(
    "ELASTICSEARCH_NUMBER_OF_SHARDS", default=1
)
ELASTICSEARCH_NUMBER_OF_REPLICAS = env(
    "ELASTICSEARCH_NUMBER_OF_REPLICAS", default=0
)

# Oral Arguments Search index shards and replicas
ELASTICSEARCH_OA_NUMBER_OF_SHARDS = env(
    "ELASTICSEARCH_OA_NUMBER_OF_SHARDS", default=1
)
ELASTICSEARCH_OA_NUMBER_OF_REPLICAS = env(
    "ELASTICSEARCH_OA_NUMBER_OF_REPLICAS", default=0
)

# Oral Arguments Alerts index shards and replicas
ELASTICSEARCH_OA_ALERTS_NUMBER_OF_SHARDS = env(
    "ELASTICSEARCH_OA_ALERTS_NUMBER_OF_SHARDS", default=1
)
ELASTICSEARCH_OA_ALERTS_NUMBER_OF_REPLICAS = env(
    "ELASTICSEARCH_OA_ALERTS_NUMBER_OF_REPLICAS", default=0
)

# RECAP Search index shards and replicas
ELASTICSEARCH_RECAP_NUMBER_OF_SHARDS = env(
    "ELASTICSEARCH_RECAP_NUMBER_OF_SHARDS", default=1
)
ELASTICSEARCH_RECAP_NUMBER_OF_REPLICAS = env(
    "ELASTICSEARCH_RECAP_NUMBER_OF_REPLICAS", default=0
)


# People Search index shards and replicas
ELASTICSEARCH_PEOPLE_NUMBER_OF_SHARDS = env(
    "ELASTICSEARCH_PEOPLE_NUMBER_OF_SHARDS", default=1
)
ELASTICSEARCH_PEOPLE_NUMBER_OF_REPLICAS = env(
    "ELASTICSEARCH_PEOPLE_NUMBER_OF_REPLICAS", default=0
)

# Opinions Search index shards and replicas
ELASTICSEARCH_OPINION_NUMBER_OF_SHARDS = env(
    "ELASTICSEARCH_OPINION_NUMBER_OF_SHARDS", default=1
)
ELASTICSEARCH_OPINION_NUMBER_OF_REPLICAS = env(
    "ELASTICSEARCH_OPINION_NUMBER_OF_REPLICAS", default=0
)

# RECAP Alerts Percolator index shards and replicas
ELASTICSEARCH_RECAP_ALERTS_NUMBER_OF_SHARDS = env(
    "ELASTICSEARCH_RECAP_ALERTS_NUMBER_OF_SHARDS", default=1
)
ELASTICSEARCH_RECAP_ALERTS_NUMBER_OF_REPLICAS = env(
    "ELASTICSEARCH_RECAP_ALERTS_NUMBER_OF_REPLICAS", default=0
)


# ES Auto refresh. In production, it's suggested to wait for ES periodically
# refresh (every ~1 second) since it's a resource-intensive operation.
# This setting is overridden for testing.
# https://www.elastic.co/guide/en/elasticsearch/reference/current/indices-refresh.html#refresh-api-desc
ELASTICSEARCH_DSL_AUTO_REFRESH = env(
    "ELASTICSEARCH_DSL_AUTO_REFRESH", default=True
)

#############################################################
# Batch size for Elasticsearch queries utilizing pagination #
# such as Percolator              #
#############################################################
ELASTICSEARCH_PAGINATION_BATCH_SIZE = 100

###########################
# Search Alerts settings #
###########################
# The maximum number of scheduled hits per alert.
SCHEDULED_ALERT_HITS_LIMIT = 20

PERCOLATOR_RECAP_SEARCH_ALERTS_ENABLED = env(
    "PERCOLATOR_RECAP_SEARCH_ALERTS_ENABLED", default=False
)

################################
# ES bulk indexing batch size #
################################
ELASTICSEARCH_BULK_BATCH_SIZE = env(
    "ELASTICSEARCH_BULK_BATCH_SIZE", default=200
)

######################################################
# ES parallel bulk indexing number of threads to use #
######################################################
ELASTICSEARCH_PARALLEL_BULK_THREADS = env(
    "ELASTICSEARCH_PARALLEL_BULK_THREADS", default=5
)


##########################
# Sweep indexer settings #
##########################
ELASTICSEARCH_SWEEP_INDEXER_ACTION = env(
    "ELASTICSEARCH_SWEEP_INDEXER_ACTION", default="all"
)
ELASTICSEARCH_SWEEP_INDEXER_QUEUE = env(
    "ELASTICSEARCH_SWEEP_INDEXER_QUEUE", default="es_sweep"
)
ELASTICSEARCH_SWEEP_INDEXER_CHUNK_SIZE = env(
    "ELASTICSEARCH_SWEEP_INDEXER_CHUNK_SIZE", default=10
)
ELASTICSEARCH_SWEEP_INDEXER_HEADS_RATE = env(
    "ELASTICSEARCH_SWEEP_INDEXER_HEADS_RATE", default=60
)
ELASTICSEARCH_SWEEP_INDEXER_POLL_INTERVAL = env(
    "ELASTICSEARCH_SWEEP_INDEXER_POLL_INTERVAL", default=10
)
ELASTICSEARCH_SWEEP_INDEXER_WAIT_BETWEEN_CHUNKS = env(
    "ELASTICSEARCH_SWEEP_INDEXER_WAIT_BETWEEN_CHUNKS", default=3
)
ELASTICSEARCH_SWEEP_INDEXER_MODELS = env(
    "ELASTICSEARCH_SWEEP_INDEXER_MODELS",
    default=[
        "audio.Audio",
        "people_db.Person",
        "search.OpinionCluster",
        "search.Opinion",
        "search.Docket",
        "search.RECAPDocument",
    ],
)


ELASTICSEARCH_MAX_RESULT_COUNT = 10_000
ELASTICSEARCH_CARDINALITY_PRECISION = 2000

ELASTICSEARCH_MICRO_CACHE_ENABLED = env(
    "ELASTICSEARCH_MICRO_CACHE_ENABLED", default=False
)
