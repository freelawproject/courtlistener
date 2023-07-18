import environ

env = environ.FileAwareEnv()

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
        "verify_certs": True,
        "ca_certs": ELASTICSEARCH_CA_CERT,
        "request_timeout": 30,
        "retry_on_timeout": True,
        "max_retries": 5,
    },
}

ELASTICSEARCH_NUMBER_OF_SHARDS = env(
    "ELASTICSEARCH_NUMBER_OF_SHARDS", default=1
)
ELASTICSEARCH_NUMBER_OF_REPLICAS = env(
    "ELASTICSEARCH_NUMBER_OF_REPLICAS", default=0
)
