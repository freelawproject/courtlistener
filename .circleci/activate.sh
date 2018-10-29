#!/usr/bin/env bash

/etc/init.d/postgresql start
source ~/virtualenvs/courtlistener/bin/activate
exec "$@"
