# `python-base` sets up all our shared environment variables
FROM python:3.10-slim as python-base

    # Let python output be fast
ENV PYTHONUNBUFFERED=1 \
    \
    # pip
    # Disable the pip cache (yes, off is confusing)
    PIP_NO_CACHE_DIR=off \
    # Don't show the notice if there's a newer version of pip
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    \
    # poetry
    # https://python-poetry.org/docs/configuration/#using-environment-variables
    POETRY_VERSION=1.1.13 \
    # make poetry install to this location
    POETRY_HOME="/opt/poetry" \
    # Don't build a virtualenv to save space
    POETRY_VIRTUALENVS_CREATE=false \
    # do not ask any interactive question
    POETRY_NO_INTERACTION=1 \
    \
    # paths
    # this is where our requirements + virtual environment will live
    PYSETUP_PATH="/opt/pysetup" \
    VENV_PATH="/opt/pysetup/.venv"


# prepend poetry and venv to path
ENV PATH="$POETRY_HOME/bin:$VENV_PATH/bin:$PATH"

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

# install poetry - respects $POETRY_VERSION & $POETRY_HOME
RUN curl -sSL https://install.python-poetry.org | python3 -

# copy project requirement files here to ensure they will be cached.
WORKDIR $PYSETUP_PATH
COPY poetry.lock pyproject.toml ./

# install runtime deps - uses $POETRY_VIRTUALENVS_IN_PROJECT internally
RUN poetry install --no-root && \
    poetry install --no-root --extras flp

# will become mountpoint of our code
WORKDIR /opt

# We log to stdout by default, but we have a config for logging here. Even if
# we don't use this logger, we need to have the file or else Python is unhappy.
RUN mkdir /var/log/courtlistener \
  && chown -R www-data:www-data /var/log/courtlistener \
  && mkdir /var/log/juriscraper \
  && chown -R www-data:www-data /var/log/juriscraper/ \
  && mkdir -p /opt/courtlistener/cl/assets/static/

CMD python /opt/courtlistener/manage.py runserver 0.0.0.0:8000
