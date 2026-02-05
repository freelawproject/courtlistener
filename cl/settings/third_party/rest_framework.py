import environ

env = environ.FileAwareEnv()
DEVELOPMENT = env.bool("DEVELOPMENT", default=True)

#######
# API #
#######
REST_FRAMEWORK = {
    # Use Django's standard `django.contrib.auth` permissions,
    # or allow read-only access for unauthenticated users.
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.DjangoModelPermissionsOrAnonReadOnly"
    ],
    # Versioning
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.URLPathVersioning",
    "DEFAULT_VERSION": "v3",
    "ALLOWED_VERSIONS": {"v3", "v4"},
    # Throttles
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "cl.api.utils.ExceptionalUserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/day",
        "user": "5000/hour",
        "citations": "60/min",
    },
    # Auth
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.BasicAuthentication",
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    # Rendering and Parsing
    "DEFAULT_PARSER_CLASSES": (
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework_xml.parsers.XMLParser",
    ),
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
        "rest_framework_xml.renderers.XMLRenderer",
    ),
    # Filtering
    "DEFAULT_FILTER_BACKENDS": (
        # DisabledHTMLFilterBackend disables showing filters in the browsable API
        "cl.api.utils.DisabledHTMLFilterBackend",
        # Validates query params and logs/blocks unknown filter parameters
        "cl.api.utils.UnknownFilterParamValidationBackend",
        "rest_framework.filters.OrderingFilter",
    ),
    # Assorted & Sundry
    "DEFAULT_PAGINATION_CLASS": "cl.api.pagination.VersionBasedPagination",
    "PAGE_SIZE": 20,
    "URL_FIELD_NAME": "resource_uri",
    "DEFAULT_METADATA_CLASS": "cl.api.utils.SimpleMetadataWithFilters",
    "ORDERING_PARAM": "order_by",
    "HTML_SELECT_CUTOFF": 100,
    "UPLOADED_FILES_USE_URL": False,
}

if DEVELOPMENT:
    REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["anon"] = "10000/day"  # type: ignore

BLOCK_NEW_V3_USERS = env.bool("BLOCK_NEW_V3_USERS", default=False)

# Controls whether unknown API filter parameters should be blocked (400 error)
# or just logged. Set to True to block invalid filter parameters.
# Phase 1: False (log only), Phase 2: True (block requests)
BLOCK_UNKNOWN_FILTERS = env.bool("BLOCK_UNKNOWN_FILTERS", default=False)
