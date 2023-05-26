ARG BUILD_ENV=prod

FROM python:3.10-slim as build-base

RUN apt-get update --option "Acquire::Retries=3" --quiet=2 && \
    apt-get install \
        --no-install-recommends \
        --assume-yes \
        --quiet=2 \
        # So we can use Python-slim
        build-essential gcc python3-dev\
        # So postgres can compile and users can use dbshell
        libpq-dev postgresql-client \
        # For installing poetry and git-based deps
        curl git \
        # Other dependencies
        libffi-dev libxml2-dev libxslt-dev procps vim cmake

# poetry
# https://python-poetry.org/docs/configuration/#using-environment-variables
ENV POETRY_VERSION=1.5.0 \
    # make poetry install to this location
    POETRY_HOME="/opt/poetry" \
    # Don't build a virtualenv to save space
    POETRY_VIRTUALENVS_CREATE=false \
    # do not ask any interactive question
    POETRY_NO_INTERACTION=1

# install poetry - respects $POETRY_VERSION & $POETRY_HOME
RUN curl -sSL https://install.python-poetry.org | python3 -

ARG POETRY_HOME

ENV PYTHONUNBUFFERED=1 \
    # paths
    # where to create the env
    VENV_PATH="/opt/pysetup/.venv" \
    # this is where our requirements + virtual environment will live
    PYSETUP_PATH="/opt/pysetup"

# prepend poetry and venv to path
ENV PATH="/opt/poetry/bin:$VENV_PATH/bin:$PATH"


FROM build-base as build-dev

WORKDIR $PYSETUP_PATH

COPY poetry.lock pyproject.toml ./
RUN poetry install --no-root

COPY . /opt/courtlistener


FROM build-base as build-prod

WORKDIR $PYSETUP_PATH

# copy project requirement files here to ensure they will be cached.
ADD https://raw.githubusercontent.com/freelawproject/courtlistener/main/poetry.lock /opt/poetry.lock
ADD https://raw.githubusercontent.com/freelawproject/courtlistener/main/pyproject.toml /opt/pyproject.toml

# install runtime deps - uses $POETRY_VIRTUALENVS_IN_PROJECT internally
RUN poetry install --no-root --without dev

ADD https://github.com/freelawproject/courtlistener/archive/main.tar.gz /opt/courtlistener.tar.gz
WORKDIR /opt
RUN tar xvfz courtlistener.tar.gz && \
    mv /opt/courtlistener-main /opt/courtlistener && \
    rm -r /opt/courtlistener.tar.gz

# `python-base` sets up all our shared environment variables
FROM build-${BUILD_ENV} as python-base

WORKDIR /opt

# We log to stdout by default, but we have a config for logging here. Even if
# we don't use this logger, we need to have the file or else Python is unhappy.
RUN mkdir /var/log/courtlistener \
  && chown -R www-data:www-data /var/log/courtlistener \
  && mkdir /var/log/juriscraper \
  && chown -R www-data:www-data /var/log/juriscraper/ \
  && mkdir -p /opt/courtlistener/cl/assets/static/

WORKDIR /opt/courtlistener

# freelawproject/courtlistener:latest-celery
FROM python-base as celery

## Needs to be two commands so second one can use variables from first.
ENV PYTHONPATH="${PYTHONPATH}:/opt/courtlistener"
USER 33

CMD celery \
    --app=cl worker \
    --loglevel=info \
    --events \
    --pool=prefork \
    --hostname=prefork@%h \
    --queues=${CELERY_QUEUES} \
    --concurrency=${CELERY_PREFORK_CONCURRENCY:-0} \
    --prefetch-multiplier=${CELERY_PREFETCH_MULTIPLIER:-1}

#freelawproject/courtlistener:latest-web-dev
FROM python-base as web-dev

CMD python /opt/courtlistener/manage.py migrate && \
    python /opt/courtlistener/manage.py createcachetable && \
    python /opt/courtlistener/manage.py runserver 0.0.0.0:8000

#freelawproject/courtlistener:latest-web-prod
FROM python-base as web-prod

CMD gunicorn cl_wsgi:application \
    --chdir /opt/courtlistener/docker/django/wsgi-configs/ \
    --user www-data \
    --group www-data \
    # Set high number of workers. Docs recommend 2-4× core count`
    --workers ${NUM_WORKERS:-48} \
    --worker-class gthread \
    --threads 2 \
    # Allow longer queries to solr.
    --limit-request-line 6000 \
    # Reset each worker once in a while
    --max-requests 10000 \
    --max-requests-jitter 100 \
    --timeout 180 \
    --bind 0.0.0.0:8000

#freelawproject/courtlistener:latest-scrape-rss
FROM python-base as rss-scraper

USER www-data
CMD /opt/courtlistener/manage.py scrape_rss


FROM python-base as retry-webhooks

USER www-data
CMD /opt/courtlistener/manage.py cl_retry_webhooks
