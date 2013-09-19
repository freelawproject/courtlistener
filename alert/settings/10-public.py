# Celery imports
import djcelery
djcelery.setup_loader()
# Needed by Celery to avoid using relative path imports. See:
# http://docs.celeryq.org/en/latest/userguide/tasks.html#automatic-naming-and-relative-imports
import os
import sys
sys.path.append(os.getcwd())

# Loads the variable INSTALL_ROOT
execfile('/etc/courtlistener')

SITE_ID = 1

# If you set this to False, Django will make some optimizations so as not
# to load the internationalization machinery.
USE_I18N = False
DEFAULT_CHARSET = 'utf-8'
LANGUAGE_CODE = 'en-us'

# List of callables that know how to import templates from various sources.
TEMPLATE_LOADERS = (
    'django.template.loaders.filesystem.Loader',
    'django.template.loaders.app_directories.Loader',
)

TEMPLATE_CONTEXT_PROCESSORS = (
    'django.contrib.messages.context_processors.messages',
    'django.contrib.auth.context_processors.auth',
    'django.core.context_processors.request',
    'django.core.context_processors.static',
)

MIDDLEWARE_CLASSES = (
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.middleware.cache.UpdateCacheMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.contrib.flatpages.middleware.FlatpageFallbackMiddleware',
    'django.middleware.cache.FetchFromCacheMiddleware',
    'debug_toolbar.middleware.DebugToolbarMiddleware',
)

ROOT_URLCONF = 'alert.urls'

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.admindocs',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.flatpages',
    'django.contrib.humanize',
    'django.contrib.messages',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.sitemaps',
    'django.contrib.staticfiles',
    'djcelery',
    'debug_toolbar',
    'south',
    'alerts',
    'api',
    'casepage',
    'citations',
    'corpus_importer',
    'contact',
    'coverage',
    'custom_filters',
    'donate',
    'favorites',
    'honeypot',
    'lib',
    'maintenance_warning',
    'pinger',
    'scrapers',
    'search',
    'userHandling',
]


# This is where the @login_required decorator redirects. By default it's /accounts/login.
# Also where users are redirected after they login. Default: /account/profile
LOGIN_URL = "/sign-in/"
LOGIN_REDIRECT_URL = "/"

# Per documentation, we need this to extend the User model
# (http://docs.djangoproject.com/en/dev/topics/auth/#storing-additional-information-about-users)
AUTH_PROFILE_MODULE = 'userHandling.UserProfile'

# These remap some of the the messages constants to correspond with blueprint
from django.contrib.messages import constants as message_constants
MESSAGE_TAGS = {
    message_constants.DEBUG: 'notice',
    message_constants.INFO: 'notice',
    message_constants.WARNING: 'error',
}

########
# Solr #
########
SOLR_URL = 'http://127.0.0.1:8983/solr/collection1'
#SOLR_URL = 'http://127.0.0.1:8983/solr/swap_core'


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
    CELERYD_CONCURRENCY = 24

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
    'http://search.yahooapis.com/SiteExplorerService/V1/ping',
    'http://www.google.com/webmasters/tools/ping',
    'http://www.bing.com/webmaster/ping.aspx',
)


###############
# Directories #
###############
MEDIA_ROOT = os.path.join(INSTALL_ROOT, 'alert/assets/media/')

# Static files configuration...
STATIC_URL = '/static/'
STATICFILES_DIRS = (os.path.join(INSTALL_ROOT, 'alert/assets/static-global/'),)
STATIC_ROOT = os.path.join(INSTALL_ROOT, 'alert/assets/static/')  # This is where things get collected to

# Where should the data dumps be stored?
DUMP_DIR = os.path.join(INSTALL_ROOT, 'alert/assets/media/dumps/')

TEMPLATE_DIRS = (
    # Don't forget to use absolute paths, not relative paths.
    os.path.join(INSTALL_ROOT, 'alert/assets/templates/'),
)


############
# Payments #
############
PAYMENT_REDIRECT = 'https://www.courtlistener.com/donate/thanks/'
PAYMENT_CANCELLATION = 'https://www.courtlistener.com/donate/cancel/'
DWOLLA_CALLBACK = 'https://www.courtlistener.com/donate/callbacks/dwolla/'
PAYPAL_CALLBACK = 'https://www.courtlistener.com/donate/callbacks/paypal/'
DWOLLA_REDIRECT = 'https://www.courtlistener.com/donate/dwolla/complete/'


######################
# Various and Sundry #
######################
if DEVELOPMENT:
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_DOMAIN = '127.0.0.1'
    CSRF_COOKIE_SECURE = False
    # For debug_toolbar
    INTERNAL_IPS = ('127.0.0.1',)
    DEBUG_TOOLBAR_CONFIG = {'INTERCEPT_REDIRECTS': False}
    # For tests
    SOUTH_TESTS_MIGRATE = False
    if 'test' in sys.argv:
        # Does DB in memory during tests
        DATABASES['default'] = {'ENGINE': 'django.db.backends.sqlite3'}
else:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    DEBUG_TOOLBAR_CONFIG = {'INTERCEPT_REDIRECTS': False}


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


