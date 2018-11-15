#!/usr/bin/env bash
set -e

mkdir -p /var/log/courtlistener

# Install required debian packages.
apt-get update -qq && apt-get install -y --no-install-recommends \
  build-essential \
  git \
  libpq-dev \
  libxml2-dev \
  libxslt1-dev \
  python-dev \
  python-pip \
  zlib1g-dev

# Install, create, and activate a virtualenv.
pip install virtualenv
virtualenv ~/virtualenvs/courtlistener
source ~/virtualenvs/courtlistener/bin/activate

pip install -r /tmp/requirements.txt
pip install -r /tmp/requirements-test.txt
# This dependency isn't in the requirements file for some reason.
pip install git+https://github.com/freelawproject/judge-pics@master
