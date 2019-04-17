#!/usr/bin/env bash
set -e

# Add the postgresql repository
apt-get update -qq && apt-get install -y wget
mv /var/circleci/pgdg.list /etc/apt/sources.list.d/pgdg.list
wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add -


apt-get update -qq && apt-get install -y --no-install-recommends \
  postgresql-10 \
  python-psycopg2
/etc/init.d/postgresql start

# Do this first before we change pg_hba.conf so we can guarantee we have the right password.
su postgres -c "psql -U postgres -c \"ALTER USER postgres WITH ENCRYPTED PASSWORD 'password';\""
mv /var/circleci/pg_hba.conf /etc/postgresql/10/main/pg_hba.conf
chown postgres:postgres /etc/postgresql/10/main/pg_hba.conf
mv /var/circleci/pgpass ~/.pgpass
chmod 600 ~/.pgpass
/etc/init.d/postgresql restart

# Create django user and courtlistener database
psql -U postgres -c "CREATE USER django WITH PASSWORD 'your-password' CREATEDB NOSUPERUSER;"
psql -U postgres -c "CREATE DATABASE courtlistener WITH OWNER django TEMPLATE template0 ENCODING 'UTF-8';"
psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE courtlistener to django;"
