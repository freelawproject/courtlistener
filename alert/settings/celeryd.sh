#!/bin/sh
# Name of nodes to start, here we have a single node
CELERYD_NODES="w1"

ENV_PYTHON="python"
# If you are using a virtual environment, comment out the line above and uncomment
# the folling line, substituting in the path to your virtual environment.
#ENV_PYTHON="/path/to/my/virtualenv/bin/python"

# Get the INSTALL_ROOT
. /etc/courtlistener
if [ -z $INSTALL_ROOT ]; then
  echo "INSTALL_ROOT is not set. Please set it in /etc/courtlistener."
  exit 1
fi

# How to call "manage.py celeryd_multi"
CELERYD_MULTI="$ENV_PYTHON $INSTALL_ROOT/manage.py celeryd_multi"

# %n will be replaced with the nodename.
CELERYD_LOG_FILE="/var/log/celery/%n.log"
CELERYD_LOG_LEVEL="INFO"
CELERYD_PID_FILE="/var/run/celery/celery@%n.pid"

# Workers should run as an unprivileged user.
CELERYD_USER="www-data"
CELERYD_GROUP="www-data"

# Name of the projects settings module.
export DJANGO_SETTINGS_MODULE="alert.settings"
