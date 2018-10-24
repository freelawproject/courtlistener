#!/usr/bin/env bash

/etc/init.d/postgresql start
source /var/www/.virtualenvs/courtlistener/bin/activate
exec "$@"
