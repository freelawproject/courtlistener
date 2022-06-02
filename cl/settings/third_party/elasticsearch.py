import environ

env = environ.FileAwareEnv()

ELASTICSEARCH_DSL_HOST = env("ELASTICSEARCH_DSL_HOST", default="localhost")
ELASTICSEARCH_DSL_PORT = env("ELASTICSEARCH_DSL_PORT", default="9200")

ELASTICSEARCH_DSL = {
    'default': {
        'hosts': f"{ELASTICSEARCH_DSL_HOST}:{ELASTICSEARCH_DSL_PORT}"
    },
}
