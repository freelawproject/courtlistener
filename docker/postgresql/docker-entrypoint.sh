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

# Run PostgreSQL
docker-entrypoint.sh postgres
