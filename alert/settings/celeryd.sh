# Name of nodes to start, here we have a single node
CELERYD_NODES="w1"

# How to call "manage.py celeryd_multi"
CELERYD_MULTI="python /var/www/court-listener/alert/manage.py celeryd_multi"

# Name of the celery config module.
CELERY_CONFIG_MODULE="celeryconfig"

# %n will be replaced with the nodename.
CELERYD_LOG_FILE="/var/log/celery/%n.log"
CELERYD_LOG_LEVEL="INFO"
CELERYD_PID_FILE="/var/run/celery/celery@%n.pid"

# Workers should run as an unprivileged user.
CELERYD_USER="celery"
CELERYD_GROUP="celery"

# Name of the projects settings module.
export DJANGO_SETTINGS_MODULE="settings"
