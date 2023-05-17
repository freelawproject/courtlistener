import environ

env = environ.FileAwareEnv()

ELASTICSEARCH_DSL_HOST = env("ELASTICSEARCH_DSL_HOST", default="cl-es")
ELASTICSEARCH_DSL_PORT = env("ELASTICSEARCH_DSL_PORT", default="9200")

ELASTICSEARCH_DSL = {
    "default": {"hosts": f"{ELASTICSEARCH_DSL_HOST}:{ELASTICSEARCH_DSL_PORT}"},
    "analysis": {
        "analyzer": {
            "text_en_splitting_cl": {
                "type": "custom",
                "tokenizer": "whitespace",
                "filter": [
                    "lowercase",
                    "synonym_filter",
                    "word_delimiter",
                    "remove_leading_zeros",
                    "keyword_marker",
                    "english_stemmer",
                    "english_stop",
                    "remove_duplicates",
                ],
            },
        },
        "filter": {
            "english_stop": {
                "type": "stop",
                "stopwords_path": "stopwords_en.txt",
            },
            "synonym_filter": {
                "type": "synonym",
                "synonyms_path": "synonyms_en.txt",
            },
            "keyword_marker": {
                "type": "keyword_marker",
                "keywords_path": "protwords_en.txt",
            },
            "english_stemmer": {"type": "stemmer", "language": "english"},
            "remove_duplicates": {"type": "unique"},
            "remove_leading_zeros": {
                "type": "pattern_replace",
                "pattern": "^0*",
                "replacement": "",
            },
        },
    },
}

ELASTICSEARCH_NUMBER_OF_SHARDS = env(
    "ELASTICSEARCH_NUMBER_OF_SHARDS", default=1
)
ELASTICSEARCH_NUMBER_OF_REPLICAS = env(
    "ELASTICSEARCH_NUMBER_OF_REPLICAS", default=0
)
