FROM python:3.13 AS build-base

# Install apt dependencies
# caching: https://docs.docker.com/build/cache/optimize/#use-cache-mounts
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update --quiet=2 && \
    apt-get install \
    --no-install-recommends \
    --assume-yes \
    --quiet=2 \
    # So postgres can compile and users can use dbshell
    libpq-dev postgresql-client \
    # So we can use webpack to compile assets
    nodejs npm \
    # For installing git-based deps
    curl git \
    # For maintenance tasks \
    screen redis-tools vim \
    # Other dependencies
    libffi-dev libxml2-dev libxslt-dev procps cmake

# Install uv
# https://docs.astral.sh/uv/guides/integration/docker/#installing-uv
COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /uvx /bin/

ENV \
    # Set PGSSLCERT at a dummy location ro avoid a SSL error connection.
    # https://github.com/freelawproject/courtlistener/issues/2827
    PGSSLCERT=/tmp/postgresql.crt \
    # Unbuffer Python output for instant logging
    PYTHONUNBUFFERED=1

ARG BUILD_ENV=prod
FROM build-base AS python-base

WORKDIR /opt/courtlistener

# uv install dependencies
COPY pyproject.toml uv.lock .
# https://docs.astral.sh/uv/guides/integration/docker/#caching
ENV \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync \
    $(test "$BUILD_ENV" != "dev" && echo "--no-dev")

# npm install dependencies
COPY cl/package.json cl/package-lock.json ./cl/
RUN cd cl && \
    npm ci

COPY . .

# Run Node.js build tasks
# Note: Always produce production code and never produce source-maps
# (run the devMiddleware for legible output)
RUN cd cl && \
    npx webpack --mode=production --no-devtool && \
    npm run build --no-input

# We log to stdout by default, but we have a config for logging here. Even if
# we don't use this logger, we need to have the file or else Python is unhappy.
RUN mkdir /var/log/courtlistener \
    && chown -R www-data:www-data /var/log/courtlistener \
    && mkdir /var/log/juriscraper \
    && chown -R www-data:www-data /var/log/juriscraper/ \
    && mkdir -p /opt/courtlistener/cl/assets/static/

USER root
## Creates a directory for Hyperscan db
RUN mkdir /opt/courtlistener/.hyperscan \
    && chown -R www-data:www-data /opt/courtlistener/.hyperscan
RUN chmod +x /opt/courtlistener/docker/django/docker-entrypoint.sh
RUN chown www-data:www-data /opt/courtlistener/docker/django/docker-entrypoint.sh

USER www-data
ENTRYPOINT ["/bin/sh", "/opt/courtlistener/docker/django/docker-entrypoint.sh"]
