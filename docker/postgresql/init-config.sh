#!/bin/bash
set -e

# Update the PostgreSQL configuration to add SSL support and use self-signed SSL certificate
sed -i "s|^#ssl = off|ssl = on|" /var/lib/postgresql/data/postgresql.conf
sed -i "s|^#ssl_cert_file =.*|ssl_cert_file = '/var/lib/postgresql/ssl/server.crt'|" /var/lib/postgresql/data/postgresql.conf
sed -i "s|^#ssl_key_file =.*|ssl_key_file = '/var/lib/postgresql/ssl/server.req'|" /var/lib/postgresql/data/postgresql.conf
