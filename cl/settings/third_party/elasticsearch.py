import environ

env = environ.FileAwareEnv()

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
}

#
# Scaling/availability settings
#
ELASTICSEARCH_NUMBER_OF_SHARDS = env(
    "ELASTICSEARCH_NUMBER_OF_SHARDS", default=1
)
ELASTICSEARCH_NUMBER_OF_REPLICAS = env(
    "ELASTICSEARCH_NUMBER_OF_REPLICAS", default=0
)

# ES Auto refresh. In production, it's suggested to wait for ES periodically
# refresh (every ~1 second) since it's a resource-intensive operation.
# This setting is overridden for testing.
# https://www.elastic.co/guide/en/elasticsearch/reference/current/indices-refresh.html#refresh-api-desc
ELASTICSEARCH_DSL_AUTO_REFRESH = env(
    "ELASTICSEARCH_DSL_AUTO_REFRESH", default=True
)
