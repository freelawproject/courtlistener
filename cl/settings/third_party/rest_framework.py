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
    "OVERRIDE_THROTTLE_RATES": {
        # Throttling down.
        # Sock puppets
        "Kejik5": "1/hour",
        "PRpl.Kane": "1/hour",
        "PeterZH": "1/hour",
        "Bruno_ros": "1/hour",
        "Aziret": "1/hour",
        "kokonag227": "1/hour",
        "dedadi7242": "1/hour",
        "texoya9545": "1/hour",
        "nedah94680": "1/hour",
        "robowiy352": "1/hour",
        "cl_api_5": "1/hour",
        "cl_api_4": "1/hour",
        "cl_api_1": "1/hour",
        "cl_api_2": "1/hour",
        "cl_api_3": "1/hour",
        # Multiple accounts
        "court_account_n1": "1/hour",
        "court_account_n2": "1/hour",
        "sophia@newyorklawreview.com": "1/hour",
        "gab@newyorklawreview.com": "1/hour",
        "james@newyorklawreview.com": "1/hour",
        "my_yancy_lost": "1/hour",
        "theworky_1980": "1/hour",
        "thelaw_2025": "1/hour",
        "world_over_eggs": "1/hour",
        "yancy_closer": "1/hour",
        "phx_major": "1/hour",
        "giraffe_counsel_2025": "1/hour",
        "yoway_3897": "1/hour",
        "deantaylor2025": "1/hour",
        "yoway_3897": "1/hour",
        "api_1": "1/hour",
        "api_2": "1/hour",
        "api_account_1": "1/hour",
        "api_account_2": "1/hour",
        "api_account_3": "1/hour",
        "api_account_4": "1/hour",
        "api_account_5": "1/hour",
        "court_test_account_3": "1/hour",
        "court_test_account_2": "1/hour",
        "court_api_1": "1/hour",
        "court_api_2": "1/hour",
        "court_api_3": "1/hour",
        "court_api_4": "1/hour",
        "court_api_5": "1/hour",
        "JamesBond": "1/hour",
        "JackSparrow": "1/hour",
        "PeterPan": "1/hour",
        "HomerSimpson": "1/hour",
        "BruceWayne": "1/hour",
        "mibefis809": "1/hour",
        # Unresponsive
        "angelsburger": "1/hour",
        "patrielburger": "1/hour",
        "redchair255": "1/hour",
        "rapsanetwork": "1/hour",
        "courtlistener_api": "1/hour",
        "bobjase24": "1/hour",
        "bobjase25": "1/hour",
        "victorchaps": "1/hour",
        "AlirezaMirrokni": "1/hour",
        "court_test_account": "1/hour",
        "jmmckinnie": "1/hour",
        "projecttesting": "1/hour",
        "SAGW": "1/hour",
        # Bounced
        "riwiko8259": "1/hour",
        "xicaro7027": "1/hour",
        "nayibij851": "1/hour",
        "testname2024": "1/hour",
        "cadebe2258": "1/hour",
        # Disposable email
        "a29883f4-3958-484b-9f46-aa9796110dd0_IddU": "1/hour",
        # Didn't respond to emails, 2024-10-14
        "ashishjaddu": "10/hour",
        # Made 1M requests for commercial enterprise
        "haoren": "10/hour",
        # Used a fake email address, 2024-10-02
        "xinfu.zheng": "10/hour",
        "fdgbhgope4wuo8049": "10/hour",
        # Didn't respond to emails, 2024-08-12
        "fruitfranky": "10/hour",
        # Email non-functional; making many requests, 2024-04-23
        "NicolasMadan": "10/hour",
        # Didn't respond to emails, 2023-10-02
        "Tylersuard": "10/hour",
        # Didn't respond to emails, 2023-08-04
        "skalecorn12": "10/hour",
        # Didn't respond to emails; looks unsavory.
        "donier": "10/hour",
        # Doing a background check service, we told them we didn't want to work
        # with them.
        "elios": "10/hour",
        # Sent multiple emails, but no response.
        "bchecker": "1/hour",
        # No response
        "commernet": "1/hour",
        "zealousgalileo": "1/hour",
        "JaneDoe": "1/hour",
        "chinamkm": "1/hour",
        "shreyngd": "100/hour",
        "leo": "100/hour",
        "miffy": "100/hour",
        "safetynet": "100/hour",
        "snusbase": "1/hour",
        "gavinjburns": "1/hour",
        # Send multiple emails, but they haven't responded
        "linkfenzhao": "10/hour",
        # From fokal.ai, using multiple accounts to dodge limitations
        "manu.jose": "10/hour",
        "shishir": "10/hour",
        "shishir.kumar": "10/hour",
        # Throttling up.
        "JonasHappel": "10000/hour",
        "YFIN": "430000/day",
        "mlissner": "1000000/hour",  # Needed for benchmarking (not greed)
        "gpilapil": "10000/hour",
        "peidelman": "20000/hour",
        "waldo": "10000/hour",
        "hdave4": "15000/hour",  # GSU
        "ellliottt": "15000/hour",
        "flooie": "20000/hour",  # Needed for testing
        "WarrenLex": "20000/hour",  # For big litigation days (wow)
        "quevon24": "500000/hour",  # Perform tests, clone cases in local env
    },
    "CITATION_LOOKUP_OVERRIDE_THROTTLE_RATES": {},
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
        # This is a tweaked version of RestFrameworkFilterBackend
        "cl.api.utils.DisabledHTMLFilterBackend",
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
