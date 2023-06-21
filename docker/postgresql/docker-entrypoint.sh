#!/bin/sh
set -e

# Custom path where to store the generated SSL certificate
SSL_CERT_DIR=/var/lib/postgresql/ssl

# Generate a new self-signed SSL certificate for cl-postgres if it doesn't exist
if [ ! -f $SSL_CERT_DIR/server.crt ]; then
  mkdir -p $SSL_CERT_DIR
  openssl req -newkey rsa:2048 -nodes -x509 -keyout $SSL_CERT_DIR/server.req -out $SSL_CERT_DIR/server.crt -days 365 -subj /CN=cl-postgres
  chown postgres $SSL_CERT_DIR/server.req $SSL_CERT_DIR/server.crt
  chmod 600 $SSL_CERT_DIR/server.req $SSL_CERT_DIR/server.crt
fi

# Run PostgreSQL and capture the PID to wait for it later
docker-entrypoint.sh postgres &
POSTGRES_PID=$!

# Wait for PostgreSQL to initialize and the configuration file to appear, so it can be modified.
while [ ! -f /var/lib/postgresql/data/postgresql.conf ]; do
  sleep 1
done

# Update the PostgreSQL configuration to add SSL support and use self-signed SSL certificate
sed -i "s|^#ssl = off|ssl = on|" /var/lib/postgresql/data/postgresql.conf
sed -i "s|^#ssl_cert_file =.*|ssl_cert_file = '/var/lib/postgresql/ssl/server.crt'|" /var/lib/postgresql/data/postgresql.conf
sed -i "s|^#ssl_key_file =.*|ssl_key_file = '/var/lib/postgresql/ssl/server.req'|" /var/lib/postgresql/data/postgresql.conf

# Wait for the PostgreSQL initialization command to complete
wait $POSTGRES_PID
