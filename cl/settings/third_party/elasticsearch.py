import environ

env = environ.FileAwareEnv()

from ..django import TESTING

if TESTING:
    ELASTICSEARCH_DISABLED = True
else:
    ELASTICSEARCH_DISABLED = env(
        "ELASTICSEARCH_DISABLED",
        default=False,
    )

#
# Connection settings
#
ELASTICSEARCH_DSL_HOST = env(
    "ELASTICSEARCH_DSL_HOST",
    default=[
        "cl-es:9200",
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
ELASTICSEARCH_DSL = {
    "default": {
        "hosts": ELASTICSEARCH_DSL_HOST,
        "http_auth": (ELASTICSEARCH_USER, ELASTICSEARCH_PASSWORD),
        "use_ssl": True,
        "verify_certs": False,
        "ca_certs": ELASTICSEARCH_CA_CERT,
    },
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
            "english_exact": {
                "type": "custom",
                "tokenizer": "whitespace",
                "filter": [
                    "lowercase",
                    "custom_word_delimiter_filter",
                    "remove_leading_zeros",
                    "english_stop",
                    "remove_duplicates",
                ],
            },
        },
        "filter": {
            "custom_word_delimiter_filter": {
                "type": "word_delimiter",
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

# ES Auto refresh. In production, it's suggested to wait for ES periodically
# refresh (every ~1 second) since it's a resource-intensive operation.
# This setting is overridden for testing.
# https://www.elastic.co/guide/en/elasticsearch/reference/current/indices-refresh.html#refresh-api-desc
ELASTICSEARCH_DSL_AUTO_REFRESH = env(
    "ELASTICSEARCH_DSL_AUTO_REFRESH", default=True
)

####################################
# Percolator batch size for Alerts #
####################################
PERCOLATOR_PAGE_SIZE = 100
