# Celery imports
import djcelery
djcelery.setup_loader()
import os
import re
import sys
from django.contrib.messages import constants as message_constants

# Loads the variable INSTALL_ROOT
execfile('/etc/courtlistener')

################
# Misc. Django #
################
SITE_ID = 1
USE_I18N = False
DEFAULT_CHARSET = 'utf-8'
LANGUAGE_CODE = 'en-us'
USE_TZ = True

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
    },
}]


MIDDLEWARE_CLASSES = [
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.auth.middleware.SessionAuthenticationMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.middleware.cache.UpdateCacheMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.cache.FetchFromCacheMiddleware',
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
    'djcelery',
    'tastypie',

    # CourtListener Apps
    'cl.alerts',
    'cl.audio',
    'cl.api',
    'cl.citations',
    'cl.corpus_importer',
    'cl.custom_filters',
    'cl.donate',
    'cl.favorites',
    'cl.judges',
    'cl.lib',
    'cl.opinion_page',
    'cl.scrapers',
    'cl.search',
    'cl.simple_pages',
    'cl.stats',
    'cl.users',
    'cl.visualizations',
]


# This is where the @login_required decorator redirects. By default it's
# /accounts/login. Also where users are redirected after they login. Default:
# /account/profile
LOGIN_URL = "/sign-in/"
LOGIN_REDIRECT_URL = "/"

# These remap some of the the messages constants to correspond with blueprint
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
#SOLR_OPINION_URL = 'http://127.0.0.1:8983/solr/swap_core'
SOLR_AUDIO_URL = 'http://127.0.0.1:8983/solr/audio'


##########
# CELERY #
##########
if DEVELOPMENT:
    # In a development machine, these setting make sense
    CELERY_ALWAYS_EAGER = True
    CELERY_EAGER_PROPAGATES_EXCEPTIONS = True
    CELERYD_CONCURRENCY = 2
else:
    # Celery settings for production sites
    BROKER_URL = 'amqp://celery:%s@localhost:5672//celery' % CELERY_PASSWORD
    CELERY_RESULT_BACKEND = 'amqp'
    CELERYD_CONCURRENCY = 18

# Rate limits aren't ever used, so disable them across the board for better
# performance
CELERY_DISABLE_RATE_LIMITS = True
CELERY_SEND_TASK_ERROR_EMAILS = True


#########
# Email #
#########
if DEVELOPMENT:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

SERVER_EMAIL = 'CourtListener <noreply@courtlistener.com>'
DEFAULT_FROM_EMAIL = 'CourtListener <noreply@courtlistener.com>'
SCRAPER_ADMINS = ('Juriscraper List', 'juriscraper@lists.freelawproject.org')

###############
# Directories #
###############
MEDIA_ROOT = os.path.join(INSTALL_ROOT, 'cl/assets/media/')
STATIC_URL = '/static/'
STATICFILES_DIRS = (os.path.join(INSTALL_ROOT, 'cl/assets/static-global/'),)
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
    'no_ads': 10,
}


#######
# API #
#######
TASTYPIE_DEFAULT_FORMATS = ['json', 'jsonp', 'xml']
TASTYPIE_FULL_DEBUG = True
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
            (re.compile(r'graph\s+#?(\d+)\b', re.I),
             r'/visualization/scotus-mapper/\1/md/')
        ],
    },
}

######################
# Various and Sundry #
######################
if DEVELOPMENT:
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SESSION_COOKIE_DOMAIN = None
    # For debug_toolbar
    INSTALLED_APPS.append('debug_toolbar')
    INTERNAL_IPS = ('127.0.0.1',)
    # For tests
    SOUTH_TESTS_MIGRATE = False
    if 'test' in sys.argv:
        # Does DB in memory during tests
        DATABASES['default'] = {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': 'sqlite_db',
        }
        del DATABASES['old']

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
        'propogate': True,
    }


