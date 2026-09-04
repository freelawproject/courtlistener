#!/usr/bin/env python3
"""SessionStart hook for Claude Code on the web.

Brings up the CourtListener development stack (docker/courtlistener) before
a web session begins, so the session has a full environment and can run the
test suite the same way CI does in .github/workflows/tests.yml. It also runs
`uv sync` so `uv run pre-commit` and `uv run pyrefly check` work on the host.

Everything it prints ends up in the session transcript. If something goes
wrong it says what and exits 0, so the session still starts and the Claude in
it can fix the cause and re-run this file itself:

    CLAUDE_CODE_REMOTE=true python3 .claude/hooks/session_start.py

It is idempotent: on a resumed session the stack is already up and this
finishes in a few seconds. It only runs in remote (web) sessions.

Assumptions about the environment, each learned from a real session:

- dockerd is installed but not running when a session starts, and after a
  resume the pid files it left behind block it from starting again.
- vm.max_map_count is 65530, below the 262144 Elasticsearch refuses to
  start without; the hook runs as root and may raise it.
- The compose file manages its own network and gives Django a healthcheck,
  so `docker compose up --wait` alone means "ready to run tests".
"""

from __future__ import annotations

import hashlib
import os
import secrets
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(
    os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2]
)
COMPOSE_DIR = REPO / "docker" / "courtlistener"
# Postgres on tmpfs, as in CI: sessions are ephemeral and it is faster.
COMPOSE_FILES = [
    COMPOSE_DIR / "docker-compose.yml",
    COMPOSE_DIR / "docker-compose.tmpfs.yml",
]
# The image bakes in the Python and Node dependencies; when any of these
# change, an image cached from an earlier session is stale.
IMAGE_INPUTS = [
    REPO / "pyproject.toml",
    REPO / "uv.lock",
    REPO / "cl" / "package.json",
    REPO / "cl" / "package-lock.json",
    REPO / "docker" / "django" / "Dockerfile",
    REPO / "docker" / "django" / "docker-entrypoint.sh",
]
STATE_DIR = (
    Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    / "courtlistener"
)
IMAGE_STAMP = STATE_DIR / "image-inputs.sha256"
DOCKERD_LOG = Path("/var/log/dockerd.log")
# Daemon pid files that survive a snapshot restore while the daemons don't,
# with the sockets to remove alongside them.
DAEMON_PID_FILES = {
    "dockerd": (
        Path("/var/run/docker.pid"),
        [Path("/var/run/docker.sock")],
    ),
    "containerd": (
        Path("/var/run/docker/containerd/containerd.pid"),
        [
            Path("/var/run/docker/containerd/containerd.sock"),
            Path("/var/run/docker/containerd/containerd.sock.ttrpc"),
            Path("/var/run/docker/containerd/containerd-debug.sock"),
        ],
    ),
}
ES_MIN_MAP_COUNT = 262144
BOOT_TIMEOUT_SECONDS = 1200
DOCKERD_START_TIMEOUT_SECONDS = 60


class Bail(Exception):
    """Stop the hook with a message. The session still starts."""


def log(message: str) -> None:
    """Print a line to the session transcript."""
    print(f"[courtlistener] {message}", flush=True)


def run(
    *args: str, check: bool = True, quiet: bool = False
) -> subprocess.CompletedProcess[str]:
    """Run a command, streaming its output unless `quiet`.

    With `check`, a non-zero exit raises CalledProcessError; callers that
    treat failure as a normal outcome pass check=False and read returncode.
    """
    return subprocess.run(
        args,
        check=check,
        text=True,
        stdout=subprocess.PIPE if quiet else None,
        stderr=subprocess.STDOUT if quiet else None,
    )


def compose(
    *args: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Run `docker compose` against the files the hook chose."""
    return run("docker", "compose", "--progress", "plain", *args, check=check)


def docker_ready() -> bool:
    """Whether the Docker daemon answers."""
    return run("docker", "info", check=False, quiet=True).returncode == 0


def process_name(pid: str) -> str | None:
    """The command name of a running pid, or None if there is no such process."""
    try:
        return Path(f"/proc/{pid}/comm").read_text(encoding="utf-8").strip()
    except OSError:
        return None


def clear_stale_pidfile(
    daemon: str, pidfile: Path, sockets: list[Path]
) -> None:
    """Remove a daemon's pid file unless that daemon really owns it.

    After a snapshot restore the pid may belong to an unrelated process, and
    dockerd then refuses to start (or waits forever for "its" containerd).
    """
    if not pidfile.exists():
        return
    pid = pidfile.read_text(encoding="utf-8").strip()
    if pid and process_name(pid) == daemon:
        return
    log(f"Removing a stale {daemon} pid file left by a previous session")
    for path in [pidfile, *sockets]:
        path.unlink(missing_ok=True)


def start_dockerd() -> None:
    """Start the Docker daemon if it isn't running, and wait for it."""
    if docker_ready():
        return
    if shutil.which("dockerd") is None:
        raise Bail("Docker is not installed here, so the stack can't run.")
    for daemon, (pidfile, sockets) in DAEMON_PID_FILES.items():
        clear_stale_pidfile(daemon, pidfile, sockets)
    log(f"Starting the Docker daemon (log: {DOCKERD_LOG})...")
    with DOCKERD_LOG.open("ab") as log_file:
        subprocess.Popen(
            ["dockerd"],
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    for _ in range(DOCKERD_START_TIMEOUT_SECONDS):
        if docker_ready():
            return
        time.sleep(1)
    raise Bail(f"The Docker daemon did not come up. See {DOCKERD_LOG}.")


def ensure_max_map_count() -> None:
    """Raise vm.max_map_count to what Elasticsearch requires."""
    current = int(
        Path("/proc/sys/vm/max_map_count").read_text(encoding="utf-8")
    )
    if current >= ES_MIN_MAP_COUNT:
        return
    result = run(
        "sysctl",
        "-w",
        f"vm.max_map_count={ES_MIN_MAP_COUNT}",
        check=False,
        quiet=True,
    )
    if result.returncode != 0:
        log("Could not raise vm.max_map_count; Elasticsearch may not start.")


def ensure_env_file() -> None:
    """Create .env.dev the way CI does if there isn't one yet."""
    env_file = REPO / ".env.dev"
    if env_file.exists():
        return
    log("Creating .env.dev from .env.example")
    settings = (REPO / ".env.example").read_text(encoding="utf-8")
    settings += f"SECRET_KEY={secrets.token_urlsafe(50)}\nALLOWED_HOSTS=*\n"
    env_file.write_text(settings, encoding="utf-8")


def persist_env(name: str, value: str) -> None:
    """Export a variable for the rest of the session, not just this script."""
    os.environ[name] = value
    env_file = os.environ.get("CLAUDE_ENV_FILE")
    if env_file:
        with open(env_file, "a", encoding="utf-8") as f:
            f.write(f"export {name}={shlex.quote(value)}\n")


def image_inputs_hash() -> str:
    """A digest of everything baked into the Django image."""
    digest = hashlib.sha256()
    for path in IMAGE_INPUTS:
        digest.update(path.read_bytes())
    return digest.hexdigest()


def rebuild_if_dependencies_changed(current_hash: str) -> None:
    """Rebuild the Django image when its inputs changed since it was built."""
    if (
        not IMAGE_STAMP.exists()
        or IMAGE_STAMP.read_text(encoding="utf-8") == current_hash
    ):
        return
    log("Dependencies changed since the Django image was built; rebuilding...")
    if compose("build", "cl-django", "cl-celery", check=False).returncode:
        raise Bail("Rebuilding the Django image failed.")


def show_stack_state() -> None:
    """Print container state and the tail of any stopped container's log."""
    log("Container state:")
    compose("ps", "--all", check=False)
    stopped = run(
        "docker",
        "compose",
        "ps",
        "--all",
        "--status",
        "exited",
        "--status",
        "dead",
        "-q",
        check=False,
        quiet=True,
    ).stdout.split()
    for container in stopped:
        log(f"Last log lines from stopped container {container}:")
        run("docker", "logs", "--tail", "40", container, check=False)
    log("Follow along with: docker compose logs -f cl-django")


def start_stack() -> None:
    """Bring the stack up and wait until every healthcheck passes."""
    log("Starting the stack. A fresh environment pulls the service images and")
    log(
        "builds the Django image, which takes 10-20 minutes; later sessions reuse them."
    )
    result = compose(
        "up",
        "-d",
        "--wait",
        "--wait-timeout",
        str(BOOT_TIMEOUT_SECONDS),
        check=False,
    )
    if result.returncode == 0:
        return
    show_stack_state()
    log("Hints:")
    log("  * Image pulls need these hosts reachable through the egress proxy:")
    log(
        "    registry-1.docker.io, auth.docker.io, production.cloudfront.docker.com"
    )
    log('    (check: curl -sS "$HTTPS_PROXY/__agentproxy/status")')
    log("  * Elasticsearch needs about 1 GB of memory.")
    raise Bail("docker compose up did not bring the stack to a healthy state.")


def sync_lint_tooling() -> None:
    """Install the Python environment pre-commit and pyrefly run in."""
    if shutil.which("uv") is None:
        log("uv is not installed; skipping host-side lint tooling.")
        return
    log(
        "Syncing the Python environment for pre-commit and pyrefly (uv sync)..."
    )
    ok = run("uv", "sync", "--quiet", check=False).returncode == 0
    ok = (
        ok
        and run(
            "uv",
            "run",
            "--quiet",
            "pre-commit",
            "install-hooks",
            check=False,
            quiet=True,
        ).returncode
        == 0
    )
    if not ok:
        log(
            "uv sync failed; linting on the host won't work until it is fixed."
        )


def main() -> int:
    """Run every step, reporting rather than failing when one can't finish."""
    if os.environ.get("CLAUDE_CODE_REMOTE") != "true":
        return 0
    os.chdir(REPO)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    # Make `docker compose ...` use these files from anywhere in the session.
    persist_env("COMPOSE_FILE", ":".join(str(p) for p in COMPOSE_FILES))
    persist_env("COMPOSE_PATH_SEPARATOR", ":")
    # The sandbox injects placeholder AWS variables for its own proxy. Blank
    # them so they don't reach the containers looking like real credentials.
    for name in (
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
    ):
        os.environ[name] = ""
    try:
        start_dockerd()
        ensure_max_map_count()
        ensure_env_file()
        current_hash = image_inputs_hash()
        rebuild_if_dependencies_changed(current_hash)
        start_stack()
        IMAGE_STAMP.write_text(current_hash, encoding="utf-8")
    except Bail as problem:
        log(f"PROBLEM: {problem}")
        log("The session will start anyway. To retry once fixed, run:")
        log(
            f"    CLAUDE_CODE_REMOTE=true python3 {Path(__file__).relative_to(REPO)}"
        )
        return 0
    sync_lint_tooling()
    log("Ready.")
    log("  Site:   http://localhost:8000")
    log("  Tests:  docker exec cl-django ./manage.py test cl.<app> --keepdb")
    log(
        "  Lint:   uv run pre-commit run --files <changed files>; uv run pyrefly check"
    )
    log(
        "  Stack:  docker compose ps | logs -f cl-django | exec cl-django bash"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
