# Celery imports
import djcelery
djcelery.setup_loader()
import os
import sys

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

import warnings
warnings.filterwarnings(
        'error', r"DateTimeField received a naive datetime",
        RuntimeWarning, r'django\.db\.models\.fields'
)

TEMPLATE_LOADERS = (
    'django.template.loaders.filesystem.Loader',
    'django.template.loaders.app_directories.Loader',
)

TEMPLATE_CONTEXT_PROCESSORS = (
    'django.contrib.messages.context_processors.messages',
    'django.contrib.auth.context_processors.auth',
    'django.core.context_processors.request',
    'django.core.context_processors.static',
    'lib.context_processors.inject_settings',
)

MIDDLEWARE_CLASSES = [
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.middleware.cache.UpdateCacheMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.cache.FetchFromCacheMiddleware',
]

ROOT_URLCONF = 'alert.urls'

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
    'djcelery',
    'south',
    'tastypie',
    'alerts',
    'audio',
    'api',
    'citations',
    'corpus_importer',
    'custom_filters',
    'donate',
    'favorites',
    'lib',
    'opinion_page',
    'scrapers',
    'search',
    'simple_pages',
    'stats',
    'userHandling',
]


# This is where the @login_required decorator redirects. By default it's
# /accounts/login. Also where users are redirected after they login. Default:
# /account/profile
LOGIN_URL = "/sign-in/"
LOGIN_REDIRECT_URL = "/"

# These remap some of the the messages constants to correspond with blueprint
from django.contrib.messages import constants as message_constants
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
# Used by Solr's init script
if DEVELOPMENT:
    SOLR_XMX = '500M'
else:
    SOLR_XMX = '30G'


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

# Rate limits aren't ever used, so disable them across the board for better performance
CELERY_DISABLE_RATE_LIMITS = True
CELERY_SEND_TASK_ERROR_EMAILS = True


#########
# Email #
#########
if DEVELOPMENT:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

SERVER_EMAIL = 'CourtListener <noreply@courtlistener.com>'
DEFAULT_FROM_EMAIL = 'CourtListener <noreply@courtlistener.com>'


#######
# SEO #
#######
SITEMAP_PING_URLS = (
    #'http://search.yahooapis.com/SiteExplorerService/V1/ping',  # Broke: 2014-06-30
    'http://www.google.com/webmasters/tools/ping',
    'http://www.bing.com/webmaster/ping.aspx',
)


###############
# Directories #
###############
MEDIA_ROOT = os.path.join(INSTALL_ROOT, 'alert/assets/media/')
STATIC_URL = '/static/'
STATICFILES_DIRS = (os.path.join(INSTALL_ROOT, 'alert/assets/static-global/'),)
# This is where things get collected to
STATIC_ROOT = os.path.join(INSTALL_ROOT, 'alert/assets/static/')

# Where should the bulk data be stored?
BULK_DATA_DIR = os.path.join(INSTALL_ROOT, 'alert/assets/media/bulk-data/')

TEMPLATE_DIRS = (
    # Don't forget to use absolute paths, not relative paths.
    os.path.join(INSTALL_ROOT, 'alert/assets/templates/'),
)


############
# Payments #
############
DWOLLA_CALLBACK = 'https://www.courtlistener.com/donate/callbacks/dwolla/'
DWOLLA_REDIRECT = 'https://www.courtlistener.com/donate/dwolla/complete/'
PAYPAL_CALLBACK = 'https://www.courtlistener.com/donate/callbacks/paypal/'
PAYPAL_REDIRECT = 'https://www.courtlistener.com/donate/paypal/complete/'
PAYPAL_CANCELLATION = 'https://www.courtlistener.com/donate/paypal/cancel/'
STRIPE_REDIRECT = 'https://www.courtlistener.com/donate/stripe/complete/'

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


######################
# Various and Sundry #
######################
if DEVELOPMENT:
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SESSION_COOKIE_DOMAIN = None
    # For debug_toolbar
    MIDDLEWARE_CLASSES.append('debug_toolbar.middleware.DebugToolbarMiddleware')
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
        'alert': {
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


