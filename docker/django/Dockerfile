FROM python:3.13-slim AS build-base

RUN apt-get update --option "Acquire::Retries=3" --quiet=2 && \
    apt-get install \
    --no-install-recommends \
    --assume-yes \
    --quiet=2 \
    # So we can use Python-slim
    build-essential gcc python3-dev\
    # So postgres can compile and users can use dbshell
    libpq-dev postgresql-client \
    # So we can use webpack to compile assets
    nodejs npm \
    # For installing poetry and git-based deps
    curl git \
    # For maintenance tasks \
    screen redis-tools vim \
    # Other dependencies
    libffi-dev libxml2-dev libxslt-dev procps cmake

# Set PGSSLCERT at a dummy location ro avoid a SSL error connection.
# https://github.com/freelawproject/courtlistener/issues/2827
ENV PGSSLCERT=/tmp/postgresql.crt

# poetry
# https://python-poetry.org/docs/configuration/#using-environment-variables
ENV POETRY_VERSION=2.1.1 \
    # make poetry install to this location
    POETRY_HOME="/opt/poetry" \
    # Don't build a virtualenv to save space
    POETRY_VIRTUALENVS_CREATE=false \
    # do not ask any interactive question
    POETRY_NO_INTERACTION=1

ENV PYTHONUNBUFFERED=1 \
    # this is where our requirements are copied to
    PYSETUP_PATH="/opt/pysetup"

RUN python -m venv $POETRY_HOME && \
    $POETRY_HOME/bin/pip install poetry==$POETRY_VERSION --quiet --upgrade && \
    ln -s $POETRY_HOME/bin/poetry "$(dirname $(which python))/poetry"  # make accessible via $PATH

ARG BUILD_ENV=prod
FROM build-base AS python-base

WORKDIR $PYSETUP_PATH

COPY poetry.lock pyproject.toml ./
RUN poetry install --no-root $(test "$BUILD_ENV" != "dev" && echo "--without dev")

COPY . /opt/courtlistener


# Collect compiled assets from webpack-build stage.
# Note: Always produce production code and never produce source-maps
# (run the devMiddleware for legible output)
WORKDIR /opt/courtlistener/cl
RUN npm install
RUN npx webpack --mode=production --no-devtool
RUN npm run build --no-input

WORKDIR /opt

# We log to stdout by default, but we have a config for logging here. Even if
# we don't use this logger, we need to have the file or else Python is unhappy.
RUN mkdir /var/log/courtlistener \
    && chown -R www-data:www-data /var/log/courtlistener \
    && mkdir /var/log/juriscraper \
    && chown -R www-data:www-data /var/log/juriscraper/ \
    && mkdir -p /opt/courtlistener/cl/assets/static/

WORKDIR /opt/courtlistener


ENV PYTHONPATH="/opt/courtlistener"

USER root
## Creates a directory for Hyperscan db
RUN mkdir /opt/courtlistener/.hyperscan \
    && chown -R www-data:www-data /opt/courtlistener/.hyperscan
RUN chmod +x /opt/courtlistener/docker/django/docker-entrypoint.sh
RUN chown www-data:www-data /opt/courtlistener/docker/django/docker-entrypoint.sh

USER www-data
ENTRYPOINT ["/bin/sh", "/opt/courtlistener/docker/django/docker-entrypoint.sh"]
