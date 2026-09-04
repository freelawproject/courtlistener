# Running CourtListener with Docker Compose

This directory holds the compose files for the CourtListener development
stack. The [developer guide on the wiki][wiki] is the full walkthrough; this
page is the short version, and it is what CI does in `.github/workflows/tests.yml`.

The stack is for development only. It is not hardened for production.

[wiki]: https://wiki.free.law/c/courtlistener/dev-guide/getting-started.md

## Quick start

From the repository root:

```bash
# 1. Make your settings file. Uncomment ALLOWED_HOSTS and SECRET_KEY in it
#    (ALLOWED_HOSTS="*" is fine on a trusted machine).
cp .env.example .env.dev

# 2. Build and start everything. --wait returns once the site is serving.
#    The first run builds the Django image and can take a while.
docker compose up --wait

# 3. Give yourself some data and a login.
docker exec -it cl-django ./manage.py make_dev_data
docker exec -it cl-django ./manage.py createsuperuser
```

Then open <http://localhost:8000>. The Django admin is at `/admin/`.

`docker compose` works from the repository root (via `compose.yaml`) or from
this directory; they load the same file. The compose project is named
`courtlistener` either way.

## Running tests

```bash
# Everything except the slow selenium tests, keeping the test DB between runs
docker exec cl-django ./manage.py test cl --exclude-tag selenium --keepdb

# One app, class, or method
docker exec cl-django ./manage.py test cl.search --keepdb
docker exec cl-django ./manage.py test cl.search.tests.SearchTest.test_a_simple_text_query --keepdb
```

Tests run in parallel by default and hide log output unless you pass
`--enable-logging`. Selenium tests need the `cl-selenium` container, which is
part of the stack; watch them over VNC on port 5900 (password `secret`).

## Everyday commands

```bash
docker compose ps                         # what's running and whether it's healthy
docker compose logs -f cl-django          # follow the Django log
docker exec -it cl-django bash            # a shell in the Django container
docker exec -it cl-django ./manage.py shell
docker compose down                       # stop everything (data is kept)
docker compose down -v                    # stop everything and drop the data
docker compose build cl-django cl-celery  # rebuild after pyproject.toml/uv.lock/package.json change
```

## Options

- **In-memory postgres.** Faster tests, but the database is wiped when the
  container stops. CI uses this.

  ```bash
  docker compose -f compose.yaml -f docker/courtlistener/docker-compose.tmpfs.yml up --wait
  ```

- **Published ports.** The stack publishes four ports, bound to `127.0.0.1`
  only, so nothing else on your network can reach the dev database or search
  index (they run with default credentials). If something on your machine
  already uses one of them, move ours with an environment variable:

  | Variable           | Default | Service       |
  |--------------------|---------|---------------|
  | `CL_DJANGO_PORT`   | 8000    | Django        |
  | `CL_POSTGRES_PORT` | 5432    | PostgreSQL    |
  | `CL_ES_PORT`       | 9200    | Elasticsearch |
  | `CL_VNC_PORT`      | 5900    | Selenium VNC  |

  For example: `CL_POSTGRES_PORT=5433 docker compose up --wait`.

  To reach a port from another device on purpose (a phone on your Wi-Fi,
  say), rebind it in a personal override file, which compose picks up
  automatically and git ignores. From the repository root that file is
  `compose.override.yaml`; from this directory it is
  `docker-compose.override.yml`. The `!override` tag replaces the port list
  instead of adding to it:

  ```yaml
  services:
    cl-django:
      ports: !override
        - "0.0.0.0:8000:8000"
  ```

- **Elasticsearch won't start on Linux.** Elasticsearch needs
  `vm.max_map_count` of at least 262144. Docker Desktop sets it for you; on a
  Linux host run `sudo sysctl -w vm.max_map_count=262144`.

- **Docker Desktop memory.** Give Docker at least 4 GB of memory. The stack
  runs Elasticsearch, PostgreSQL, Redis, Celery, Django, Selenium and two
  microservices.

## How the pieces fit

Every service joins the `cl_net_overlay` network, which compose creates. The
service names are the hostnames the Django settings default to
(`cl-postgres`, `cl-redis`, `cl-es`, `cl-doctor`, `cl-selenium`, ...), so no
connection settings are needed in `.env.dev`.

`cl-django` waits for PostgreSQL, Redis and Elasticsearch to pass their
healthchecks, then runs migrations and starts `runserver`. It reports healthy
once it answers HTTP, which is what `docker compose up --wait` waits for.

The repository is bind-mounted into `cl-django` and `cl-celery` at
`/opt/courtlistener`, so code changes are picked up live. Front-end assets are
rebuilt on change by `cl-webpack` (React) and `cl-tailwind-reload` (Tailwind).

## If you set the stack up before mid-2026

The `cl_net_overlay` network used to be created by hand. Compose now owns it
and refuses to reuse a network it didn't create. Remove yours once:

```bash
docker compose down
docker network rm cl_net_overlay
docker compose up --wait
```
