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
                    "custom_word_delimiter_filter",
                    "remove_leading_zeros",
                    "english_stemmer",
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
                "type": "synonym",
                "synonyms_path": "synonyms_en.txt",
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
