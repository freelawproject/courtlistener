# `python-base` sets up all our shared environment variables
FROM python:3.8-slim as python-base

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
    POETRY_VERSION=1.1.2 \
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


# `builder-base` stage is used to build deps + create our virtual environment
FROM python-base as builder-base
RUN apt-get update --option "Acquire::Retries=3" --quiet=2 && \
    apt-get install \
        --no-install-recommends \
        --assume-yes \
        --quiet=2 \
        # So we can use Python-slim
        build-essential gcc python-dev\
        # So postgres can compile and users can use dbshell
        libpq-dev postgresql-client \
        # For installing poetry and git-based deps
        curl git \
        # Document extraction and OCR tools
        antiword docx2txt ghostscript libwpd-tools poppler-utils \
        # Filetype identification (the python library is just a wrapper)
        libmagic1 \
        # Audio extraction/manipulation tools
        ffmpeg \
        # Image & OCR tools
        imagemagick tesseract-ocr tesseract-ocr-eng \
        # Other dependencies
        libffi-dev libxml2-dev libxslt-dev

# install poetry - respects $POETRY_VERSION & $POETRY_HOME
RUN curl -sSL https://raw.githubusercontent.com/sdispater/poetry/master/get-poetry.py | python

# copy project requirement files here to ensure they will be cached.
WORKDIR $PYSETUP_PATH
COPY poetry.lock pyproject.toml ./

# install runtime deps - uses $POETRY_VIRTUALENVS_IN_PROJECT internally
RUN poetry install --no-root
RUN poetry install --no-root --extras flp

# Remove unneeded utilities to slim the image
RUN apt purge --assume-yes \
        build-essential curl gcc git python-dev \
        libffi-dev libxml2-dev libxslt-dev \
    && apt autoremove --assume-yes

# will become mountpoint of our code
WORKDIR /opt

RUN mkdir /var/log/courtlistener && \
    chmod 777 /var/log/courtlistener

CMD python /opt/courtlistener/manage.py runserver 0.0.0.0:8000
