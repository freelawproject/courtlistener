import datetime
import os
import re
import sys

from django.contrib.messages import constants as message_constants
from judge_pics import judge_root

INSTALL_ROOT = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    '..',
)

MAINTENANCE_MODE_ENABLED = False
MAINTENANCE_MODE_ALLOW_STAFF = True
MAINTENANCE_MODE_ALLOWED_IPS = []
MAINTENANCE_MODE = {
    'enabled': MAINTENANCE_MODE_ENABLED,
    'allow_staff': MAINTENANCE_MODE_ALLOW_STAFF,
    'allowed_ips': MAINTENANCE_MODE_ALLOWED_IPS,
}

################
# Misc. Django #
################
SITE_ID = 1
USE_I18N = False
DEFAULT_CHARSET = 'utf-8'
LANGUAGE_CODE = 'en-us'
USE_TZ = True
DATETIME_FORMAT = 'N j, Y, P e'

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [
        # Don't forget to use absolute paths, not relative paths.
        os.path.join(INSTALL_ROOT, 'cl/assets/templates/'),
    ],
    'APP_DIRS': True,
    'OPTIONS': {
        'context_processors': (
            'django.contrib.messages.context_processors.messages',
            'django.contrib.auth.context_processors.auth',
            'django.template.context_processors.request',
            'django.template.context_processors.static',
            'cl.lib.context_processors.inject_settings',
            'cl.lib.context_processors.inject_random_tip',
        ),
        'debug': DEBUG,
    },
}]


MIDDLEWARE_CLASSES = [
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.auth.middleware.SessionAuthenticationMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'ratelimit.middleware.RatelimitMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'cl.lib.middleware.MaintenanceModeMiddleware',
]

ROOT_URLCONF = 'cl.urls'

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.admindocs',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.humanize',
    'django.contrib.messages',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.sitemaps',
    'django.contrib.staticfiles',
    'corsheaders',
    'markdown_deux',
    'mathfilters',
    'rest_framework',
    'rest_framework.authtoken',
    'rest_framework_swagger',
    'django_filters',

    # CourtListener Apps
    'cl.alerts',
    'cl.audio',
    'cl.api',
    'cl.citations',
    'cl.cleanup',
    'cl.corpus_importer',
    'cl.custom_filters',
    'cl.donate',
    'cl.favorites',
    'cl.people_db',
    'cl.lib',
    'cl.opinion_page',
    'cl.recap',
    'cl.recap_rss',
    'cl.scrapers',
    'cl.search',
    'cl.simple_pages',
    'cl.stats',
    'cl.users',
    'cl.visualizations',
]

if DEVELOPMENT:
    INSTALLED_APPS.append('django_extensions')


# This is where the @login_required decorator redirects. By default it's
# /accounts/login. Also where users are redirected after they login. Default:
# /account/profile
LOGIN_URL = "/sign-in/"
LOGIN_REDIRECT_URL = "/"

# These remap some of the the messages constants to correspond with bootstrap
MESSAGE_TAGS = {
    message_constants.DEBUG: 'alert-warning',
    message_constants.INFO: 'alert-info',
    message_constants.SUCCESS: 'alert-success',
    message_constants.WARNING: 'alert-warning',
    message_constants.ERROR: 'alert-danger',
}

########
# Solr #
########
SOLR_OPINION_URL = 'http://127.0.0.1:8983/solr/collection1'
SOLR_AUDIO_URL = 'http://127.0.0.1:8983/solr/audio'
SOLR_PEOPLE_URL = 'http://127.0.0.1:8983/solr/person'
SOLR_RECAP_URL = 'http://127.0.0.1:8983/solr/recap'
SOLR_URLS = {
    'opinions': SOLR_OPINION_URL,
    'audio': SOLR_AUDIO_URL,
    'person': SOLR_PEOPLE_URL,
    'recap': SOLR_RECAP_URL,
}

SOLR_OPINION_TEST_CORE_NAME = 'opinion_test'
SOLR_AUDIO_TEST_CORE_NAME = 'audio_test'
SOLR_PEOPLE_TEST_CORE_NAME = 'person_test'
SOLR_RECAP_TEST_CORE_NAME = 'recap_test'

SOLR_OPINION_TEST_URL = 'http://127.0.0.1:8983/solr/opinion_test'
SOLR_AUDIO_TEST_URL = 'http://127.0.0.1:8983/solr/audio_test'
SOLR_PEOPLE_TEST_URL = 'http://127.0.0.1:8983/solr/person_test'
SOLR_RECAP_TEST_URL = 'http://127.0.0.1:8983/solr/recap_test'
SOLR_TEST_URLS = {
    'opinion': SOLR_OPINION_TEST_URL,
    'audio': SOLR_AUDIO_TEST_URL,
    'person': SOLR_PEOPLE_TEST_URL,
    'recap': SOLR_RECAP_TEST_URL,
}

#########
# Redis #
#########
# Redis is configured with 16 databases out of the box. This keeps them neatly
# mapped.
REDIS_DATABASES = {
    'CELERY': 0,
    'CACHE': 1,
    'STATS': 2,
}
REDIS_HOST = 'localhost'
REDIS_PORT = 6379


##########
# CELERY #
##########
if DEVELOPMENT:
    # In a development machine, these setting make sense
    CELERY_ALWAYS_EAGER = True  # Do all tasks immediately, no async.
    CELERY_EAGER_PROPAGATES_EXCEPTIONS = True
    CELERYD_CONCURRENCY = 2
else:
    # Celery settings for production sites
    BROKER_URL = 'redis://%s:%s/%s' % (REDIS_HOST, REDIS_PORT,
                                       REDIS_DATABASES['CELERY'])
    CELERY_RESULT_BACKEND = 'redis://%s:%s/%s' % (REDIS_HOST, REDIS_PORT,
                                                  REDIS_DATABASES['CELERY'])
    CELERYD_CONCURRENCY = 20
    BROKER_POOL_LIMIT = 30
    CELERY_TASK_RESULT_EXPIRES = 3600
    BROKER_TRANSPORT_OPTIONS = {
        # This is the length of time a task will wait to be acknowledged by a
        # worker. This value *must* be greater than the largest ETA/countdown
        # that a task may be assigned with, or else it will be run over and over
        # in a loop. Our countdowns never tend to exceed one hour.
        'visibility_timeout': 21600,  # six hours
    }

# Rate limits aren't ever used, so disable them across the board for better
# performance
CELERY_DISABLE_RATE_LIMITS = True
CELERY_SEND_TASK_ERROR_EMAILS = True


####################
# Cache & Sessions #
####################
CACHES = {
    'default': {
        'BACKEND': 'redis_cache.RedisCache',
        'LOCATION': 'localhost:6379',
        'OPTIONS': {
            'DB': REDIS_DATABASES['CACHE'],
        },
    },
}
# This sets Redis as the session backend. This is often advised against, but we
# have pretty good persistency in Redis, so it's fairly well backed up.
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'

#########
# Email #
#########
if DEVELOPMENT:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

SERVER_EMAIL = 'CourtListener <noreply@courtlistener.com>'
DEFAULT_FROM_EMAIL = 'CourtListener <noreply@courtlistener.com>'
SCRAPER_ADMINS = (
    ('Slack Juriscraper Channel', 'j9f4b5n5x7k8x2r1@flp-talk.slack.com'),
    ('PA', 'arderyp@protonmail.com'),
)

###############
# Directories #
###############
MEDIA_ROOT = os.path.join(INSTALL_ROOT, 'cl/assets/media/')
STATIC_URL = '/static/'
STATICFILES_DIRS = (
    os.path.join(INSTALL_ROOT, 'cl/assets/static-global/'),
    ('judge_pics', os.path.join(judge_root, '256')),
)
# This is where things get collected to
STATIC_ROOT = os.path.join(INSTALL_ROOT, 'cl/assets/static/')

# Where should the bulk data be stored?
BULK_DATA_DIR = os.path.join(INSTALL_ROOT, 'cl/assets/media/bulk-data/')


#####################
# Payments & Prices #
#####################
PAYPAL_CALLBACK = 'https://www.courtlistener.com/donate/callbacks/paypal/'
PAYPAL_REDIRECT = 'https://www.courtlistener.com/donate/paypal/complete/'
PAYPAL_CANCELLATION = 'https://www.courtlistener.com/donate/paypal/cancel/'
STRIPE_REDIRECT = 'https://www.courtlistener.com/donate/stripe/complete/'

MIN_DONATION = {
    'rt_alerts': 10,
}
FUNDRAISING_MODE = False


#######
# API #
#######
REST_FRAMEWORK = {
    # Use Django's standard `django.contrib.auth` permissions,
    # or allow read-only access for unauthenticated users.
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.DjangoModelPermissionsOrAnonReadOnly'
    ],

    # Versioning
    'DEFAULT_VERSIONING_CLASS': 'rest_framework.versioning.URLPathVersioning',
    'DEFAULT_VERSION': 'v3',
    'ALLOWED_VERSIONS': {'v3'},

    # Throttles
    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.AnonRateThrottle',
        'cl.api.utils.ExceptionalUserRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/day',
        'user': '5000/hour',
    },
    'OVERRIDE_THROTTLE_RATES': {
        # Throttling down.
        'leo': '100/hour',
        'miffy': '100/hour',
        'safetynet': '100/hour',

        # Throttling up.
        'gpilapil': '10000/hour',
        'peidelman': '20000/hour',
        'waldo': '10000/hour',
        'hdave4': '15000/hour',  # GSU
        'ellliottt': '15000/hour',
    },

    # Auth
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework.authentication.BasicAuthentication',
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    ),

    # Rendering and Parsing
    'DEFAULT_PARSER_CLASSES': (
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.FormParser',
        'rest_framework.parsers.MultiPartParser',
        'rest_framework_xml.parsers.XMLParser',
    ),
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
        'rest_framework_xml.renderers.XMLRenderer',
    ),

    # Filtering
    'DEFAULT_FILTER_BACKENDS': (
        'cl.api.utils.DisabledHTMLFilterBackend',
        'rest_framework.filters.OrderingFilter',
    ),

    # Assorted & Sundry
    'PAGE_SIZE': 20,
    'URL_FIELD_NAME': 'resource_uri',
    'DEFAULT_METADATA_CLASS': 'cl.api.utils.SimpleMetadataWithFilters',
    'ORDERING_PARAM': 'order_by',
    'HTML_SELECT_CUTOFF': 100,
    'UPLOADED_FILES_USE_URL': False,
}

if DEVELOPMENT:
    REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['anon'] = '10000/day'

# CORS
CORS_ORIGIN_ALLOW_ALL = True
CORS_URLS_REGEX = r'^/api/.*$'
CORS_ALLOW_METHODS = ('GET', 'OPTIONS', )
CORS_ALLOW_CREDENTIALS = True

############
# Markdown #
############
MARKDOWN_DEUX_STYLES = {
    "default": {
        "extras": {
            "code-friendly": None,
            "cuddled-lists": None,
            "footnotes": None,
            "header-ids": None,
            "link-patterns": None,
            "nofollow": None,
            "smarty-pants": None,
            "tables": None,
        },
        "safe_mode": "escape",
        "link_patterns": [
            (re.compile(r'network\s+#?(\d+)\b', re.I),
             r'/visualizations/scotus-mapper/\1/md/'),
            (re.compile(r'opinion\s+#?(\d+)\b', re.I),
             r'/opinion/\1/md/'),
        ],
    },
}


#########
# PIWIK #
#########
PIWIK_URL = 'https://piwik.courtlistener.com/piwik.php'
PIWIK_SITE_ID = '1'


########
# SCDB #
########
# SCOTUS cases after this date aren't expected to have SCDB data.
SCDB_LATEST_CASE = datetime.datetime(2017, 6, 26)


######################
# Various and Sundry #
######################
RATELIMIT_VIEW = 'cl.simple_pages.views.ratelimited'
if DEVELOPMENT:
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SESSION_COOKIE_DOMAIN = None
    # For debug_toolbar
    #INSTALLED_APPS.append('debug_toolbar')
    INTERNAL_IPS = ('127.0.0.1',)

    if 'test' in sys.argv:
        db = DATABASES['default']
        db['ENCODING'] = 'UTF8'
        db['TEST_ENCODING'] = 'UTF8'
        db['CONN_MAX_AGE'] = 0


else:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    ALLOWED_HOSTS = ['.courtlistener.com',]


########################
# Logging Machinations #
########################
# From: http://stackoverflow.com/questions/1598823/elegant-setup-of-python-logging-in-django
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '%(levelname)s %(asctime)s (%(pathname)s %(funcName)s): "%(message)s"'
        },
        'simple': {
            'format': '%(levelname)s %(message)s'
        },
    },
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse'
        }
    },
    'handlers': {
        'null': {
            'level': 'DEBUG',
            'class': 'django.utils.log.NullHandler',
        },
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple'
        },
        'log_file': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/courtlistener/django.log',
            'maxBytes': '16777216',  # 16 megabytes
            'formatter': 'verbose'
        },
        'mail_admins': {
            'level': 'ERROR',
            'filters': ['require_debug_false'],
            'class': 'django.utils.log.AdminEmailHandler',
            'include_html': True,
        }
    },
    'loggers': {
        'django.request': {
            'handlers': ['mail_admins'],
            'level': 'ERROR',
            'propagate': True,
        },
        # Disable SuspiciousOperation.DisallowedHost exception ("Invalid
        # HTTP_HOST" header messages.) This appears to be caused by clients that
        # don't support SNI, and which are browsing to other domains on the
        # server. The most relevant bad client is the googlebot.
        'django.security.DisallowedHost': {
            'handlers': ['null'],
            'propagate': False,
        },
        # This is the one that's used practically everywhere in the code.
        'cl': {
            'handlers': ['log_file'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}

if DEVELOPMENT:
    LOGGING['loggers']['django.db.backends'] = {
        'handlers': ['log_file'],
        'level': 'DEBUG',
        'propagate': False,
    }
