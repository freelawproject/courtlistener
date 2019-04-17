#!/usr/bin/env bash

service postgresql start
service redis-server start
source ~/virtualenvs/courtlistener/bin/activate
exec "$@"
