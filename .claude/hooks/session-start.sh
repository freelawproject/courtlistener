#!/bin/bash
# SessionStart hook for Claude Code on the web.
#
# Boots the CourtListener development stack (docker/courtlistener) so that a
# web session has a full environment and can run the test suite, exactly as
# CI does in .github/workflows/tests.yml. It also installs the Python tooling
# on the host so `uv run pre-commit` and `uv run pyrefly check` work.
#
# It is idempotent: on a resumed session everything is already up and this
# finishes in a few seconds. It never blocks the session from starting: on a
# problem it prints what went wrong and how to retry, then exits 0.
#
# Run it by hand to retry after fixing something:
#     CLAUDE_CODE_REMOTE=true .claude/hooks/session-start.sh
set -uo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
    exit 0
fi

REPO="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
COMPOSE_DIR="$REPO/docker/courtlistener"
# Postgres on tmpfs, as in CI: sessions are ephemeral and it is faster.
COMPOSE_FILE="$COMPOSE_DIR/docker-compose.yml:$COMPOSE_DIR/docker-compose.tmpfs.yml"
# When CI publishes a prebuilt development image (amd64 only), pull it rather
# than spending 10-20 minutes building; a local build still happens if the
# pull fails or the dependencies change (see step 4).
if [ "$(uname -m)" = "x86_64" ] && [ -f "$COMPOSE_DIR/docker-compose.prebuilt.yml" ]; then
    COMPOSE_FILE="$COMPOSE_FILE:$COMPOSE_DIR/docker-compose.prebuilt.yml"
fi
export COMPOSE_FILE COMPOSE_PATH_SEPARATOR=":"
# The sandbox injects placeholder AWS variables for its own proxy. They must
# not leak into the containers, where they would look like real credentials.
export AWS_ACCESS_KEY_ID="" AWS_SECRET_ACCESS_KEY="" AWS_SESSION_TOKEN=""

STATE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/courtlistener"
IMAGE_STAMP="$STATE_DIR/image-inputs.sha256"
DOCKERD_LOG=/var/log/dockerd.log
BOOT_TIMEOUT_SECONDS=1200
mkdir -p "$STATE_DIR"

log() { echo "[courtlistener] $*"; }

# Print diagnostics and give up without failing the session.
bail() {
    log "PROBLEM: $*"
    log "The session will start anyway. To retry once fixed, run:"
    log "    CLAUDE_CODE_REMOTE=true $REPO/.claude/hooks/session-start.sh"
    exit 0
}

# Persist a variable for the rest of the session, not just this script.
persist_env() {
    if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
        printf 'export %s=%q\n' "$1" "$2" >> "$CLAUDE_ENV_FILE"
    fi
}

compose() { docker compose --progress plain "$@"; }

django_answers() {
    # Any HTTP status means runserver is up and migrations have finished; a
    # 400 from ALLOWED_HOSTS would still count.
    curl -sS -o /dev/null --max-time 5 http://localhost:8000/ 2>/dev/null
}

show_stack_state() {
    log "Container state:"
    compose ps --all 2>/dev/null || true
    for c in $(compose ps --all --status exited --status dead -q 2>/dev/null); do
        log "Last log lines from a stopped container ($(docker inspect -f '{{.Name}}' "$c")):"
        docker logs --tail 40 "$c" 2>&1 | sed 's/^/    /'
    done
    log "Follow along with: docker compose logs -f cl-django"
}

##############################################################################
# 1. Docker daemon
##############################################################################
if ! docker info >/dev/null 2>&1; then
    command -v dockerd >/dev/null 2>&1 \
        || bail "Docker is not installed in this environment, so the compose stack can't run."
    # When the environment is restored from a snapshot, the pid files of
    # dockerd and of the containerd it manages survive while the daemons do
    # not, and those pids may now belong to unrelated processes. dockerd then
    # refuses to start (or waits forever for "its" containerd). Clear each
    # pid file unless the named daemon really owns it.
    clear_stale_pidfile() {
        pidfile=$1; daemon=$2; shift 2
        [ -f "$pidfile" ] || return 0
        old_pid=$(cat "$pidfile" 2>/dev/null || true)
        if [ -z "$old_pid" ] || [ "$(ps -o comm= -p "$old_pid" 2>/dev/null)" != "$daemon" ]; then
            log "Removing a stale $daemon pid file left by a previous session"
            rm -f "$pidfile" "$@"
        fi
    }
    clear_stale_pidfile /var/run/docker.pid dockerd /var/run/docker.sock
    clear_stale_pidfile /var/run/docker/containerd/containerd.pid containerd \
        /var/run/docker/containerd/containerd.sock \
        /var/run/docker/containerd/containerd.sock.ttrpc \
        /var/run/docker/containerd/containerd-debug.sock
    log "Starting the Docker daemon (log: $DOCKERD_LOG)..."
    nohup dockerd >"$DOCKERD_LOG" 2>&1 &
    for _ in $(seq 1 60); do
        docker info >/dev/null 2>&1 && break
        sleep 1
    done
    docker info >/dev/null 2>&1 \
        || bail "The Docker daemon did not come up. See $DOCKERD_LOG."
fi

# Elasticsearch refuses to start below this. Docker Desktop sets it for you,
# but a bare Linux VM usually doesn't.
if [ "$(cat /proc/sys/vm/max_map_count 2>/dev/null || echo 0)" -lt 262144 ]; then
    sysctl -w vm.max_map_count=262144 >/dev/null 2>&1 \
        || log "Could not raise vm.max_map_count; Elasticsearch may fail to start."
fi

##############################################################################
# 2. Settings file, same as CI
##############################################################################
if [ ! -f "$REPO/.env.dev" ]; then
    log "Creating .env.dev from .env.example"
    cp "$REPO/.env.example" "$REPO/.env.dev"
    {
        echo "SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')"
        echo "ALLOWED_HOSTS=*"
    } >> "$REPO/.env.dev"
fi

# Make `docker compose ...` work from anywhere in the session.
persist_env COMPOSE_FILE "$COMPOSE_FILE"
persist_env COMPOSE_PATH_SEPARATOR ":"

##############################################################################
# 3. The cl_net_overlay network
##############################################################################
# Older compose files declared the network external and expected you to
# create it by hand; newer ones create it themselves and refuse to adopt a
# hand-made one. Handle both so this hook works across that transition.
network_is_external() {
    compose config --format json 2>/dev/null | python3 -c '
import json, sys
cfg = json.load(sys.stdin)
net = cfg.get("networks", {}).get("cl_net_overlay", {})
sys.exit(0 if net.get("external") is True else 1)
' 2>/dev/null
}
if network_is_external; then
    docker network inspect cl_net_overlay >/dev/null 2>&1 \
        || docker network create -d bridge --attachable cl_net_overlay >/dev/null
elif docker network inspect cl_net_overlay >/dev/null 2>&1; then
    label=$(docker network inspect -f '{{index .Labels "com.docker.compose.network"}}' cl_net_overlay)
    attached=$(docker network inspect -f '{{len .Containers}}' cl_net_overlay)
    if [ -z "$label" ] && [ "$attached" = "0" ]; then
        log "Removing hand-made cl_net_overlay network so compose can own it"
        docker network rm cl_net_overlay >/dev/null
    fi
fi

##############################################################################
# 4. Rebuild the Django image when its inputs changed
##############################################################################
# The image bakes in the Python and Node dependencies. A cached image from a
# previous session is stale once those change, and `up` alone would keep
# using it.
image_inputs_hash() {
    cat "$REPO/pyproject.toml" "$REPO/uv.lock" \
        "$REPO/cl/package.json" "$REPO/cl/package-lock.json" \
        "$REPO/docker/django/Dockerfile" "$REPO/docker/django/docker-entrypoint.sh" \
        | sha256sum | cut -d' ' -f1
}
current_hash=$(image_inputs_hash)
if [ -f "$IMAGE_STAMP" ] && [ "$(cat "$IMAGE_STAMP")" != "$current_hash" ]; then
    log "Dependencies changed since the Django image was built; rebuilding (this takes a while)..."
    compose build cl-django cl-celery || bail "Rebuilding the Django image failed."
fi

##############################################################################
# 5. Start everything and wait until Django answers
##############################################################################
if django_answers; then
    log "The stack is already up."
else
    log "Starting the stack. On a fresh environment this pulls the service images and"
    log "builds the Django image, which can take 10-20 minutes; later sessions reuse them."
    if ! compose up -d --wait --wait-timeout "$BOOT_TIMEOUT_SECONDS"; then
        show_stack_state
        log "Hints:"
        log "  * Image pulls need these hosts reachable through the egress proxy:"
        log "    registry-1.docker.io, production.cloudfront.docker.com, auth.docker.io"
        log "    (check: curl -sS \"\$HTTPS_PROXY/__agentproxy/status\")"
        log "  * Elasticsearch needs ~1 GB of memory and vm.max_map_count >= 262144."
        bail "docker compose up did not bring the stack to a healthy state."
    fi
    # Compose files without a Django healthcheck return from --wait as soon
    # as the container is running, so also wait for HTTP ourselves.
    waited=0
    until django_answers; do
        if [ "$waited" -ge "$BOOT_TIMEOUT_SECONDS" ]; then
            show_stack_state
            bail "Django did not answer on http://localhost:8000 within ${BOOT_TIMEOUT_SECONDS}s."
        fi
        if [ $((waited % 30)) -eq 0 ]; then
            log "Waiting for Django (migrations run on first boot)... ${waited}s"
        fi
        sleep 5
        waited=$((waited + 5))
    done
fi
echo "$current_hash" > "$IMAGE_STAMP"

##############################################################################
# 6. Host-side tooling for linting, as in .github/workflows/lint.yml
##############################################################################
if command -v uv >/dev/null 2>&1; then
    log "Syncing the Python environment for pre-commit and pyrefly (uv sync)..."
    (cd "$REPO" && uv sync --quiet && uv run --quiet pre-commit install-hooks >/dev/null) \
        || log "uv sync failed; linting on the host won't work until it is fixed."
else
    log "uv is not installed; skipping host-side lint tooling."
fi

##############################################################################
# Done
##############################################################################
log "Ready."
log "  Site:   http://localhost:8000"
log "  Tests:  docker exec cl-django ./manage.py test cl.<app> --keepdb"
log "  Lint:   uv run pre-commit run --files <changed files>   and   uv run pyrefly check"
log "  Stack:  docker compose ps | logs -f cl-django | exec cl-django bash"
