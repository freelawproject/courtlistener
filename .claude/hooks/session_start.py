#!/usr/bin/env python3
"""SessionStart hook for Claude Code on the web.

Boots the CourtListener development stack (docker/courtlistener) for a web
session, so the session can run the test suite against a real environment
the same way CI does in .github/workflows/tests.yml. It also runs `uv sync`
so `uv run pre-commit` and `uv run pyrefly check` work on the host.

The boot runs in the background, so the session opens right away. Each new
web session starts on a fresh machine, so its first boot pulls every service
image and builds the Django image, which takes 10-20 minutes; a resumed
session reuses them and is ready in seconds. Before running tests, wait for
the stack with:

    python3 .claude/hooks/session_start.py --wait

That command is also the retry: when no boot is running it starts one, so
it recovers a failed boot or a stopped stack. One call waits at most about
nine minutes, to fit in a single tool call, and says so if the stack is
still starting; run it again to keep waiting. Stopping it never stops the
boot itself.

The hook's own output lands in the session transcript. The boot logs to
~/.cache/courtlistener/boot.log. Outside web sessions it does nothing.

Assumptions about the environment, each learned from a real session:

- dockerd is installed but not running when a session starts, and after a
  resume the pid files it left behind block it from starting again.
- vm.max_map_count is 65530, below the 262144 Elasticsearch refuses to
  start without; the hook runs as root and may raise it.
- The compose file manages its own network and gives Django a healthcheck,
  so `docker compose up --wait` alone means "ready to run tests".
- Downloads go through the environment's network policy, which can refuse
  hosts. DOWNLOAD_HOSTS lists the ones a first boot needs.
- Docker Hub rate-limits anonymous pulls from the sessions' shared IPs. The
  stack therefore boots only when DOCKERHUB_USERNAME and DOCKERHUB_TOKEN are
  set in the cloud environment's settings; otherwise the hook and --wait
  print a note explaining how to set them and boot nothing.
- The sandbox re-signs outbound TLS with its own CA and points host tools
  at the bundle through SSL_CERT_FILE. Containers don't see the host's
  trust store, so the image build and npm fail with certificate errors
  unless the stack's base images are rebuilt with the bundle installed;
  proxy-ca/ holds the Dockerfile and the compose override that swaps
  them in.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

REPO = Path(
    os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2]
)
SELF = Path(__file__).resolve()
WAIT_COMMAND = "python3 .claude/hooks/session_start.py --wait"
COMPOSE_DIR = REPO / "docker" / "courtlistener"
# Postgres on tmpfs, as in CI: sessions are ephemeral and it is faster.
COMPOSE_FILES = [
    COMPOSE_DIR / "docker-compose.yml",
    COMPOSE_DIR / "docker-compose.tmpfs.yml",
]
# The host's CA bundle when a TLS-intercepting proxy sets one, and the
# Docker Hub base images the stack uses, mapped to the tags their rebuilt,
# bundle-trusting versions get. The keys must match the FROM line in
# docker/django/Dockerfile and the node image in docker-compose.yml, which
# build_proxy_ca_images checks, since a mismatch would silently fall back
# to the untrusting originals.
HOST_CA_BUNDLE = os.environ.get("SSL_CERT_FILE", "")
PROXY_CA_DIR = Path(__file__).resolve().parent / "proxy-ca"
PROXY_CA_IMAGES = {
    "python:3.13": "cl-proxy-ca/python:3.13",
    "node:16": "cl-proxy-ca/node:16",
}
if os.path.isfile(HOST_CA_BUNDLE):
    COMPOSE_FILES.append(PROXY_CA_DIR / "docker-compose.yml")
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
BOOT_LOG = STATE_DIR / "boot.log"
BOOT_STATUS = STATE_DIR / "boot.json"
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
# Hosts a first boot downloads from: Docker Hub and GitHub's container
# registry for the images, Debian's mirrors for the Django image's packages.
DOWNLOAD_HOSTS = [
    "registry-1.docker.io",
    "auth.docker.io",
    "production.cloudfront.docker.com",
    "ghcr.io",
    "pkg-containers.githubusercontent.com",
    "deb.debian.org",
    "security.debian.org",
]
# Docker Hub rate-limits anonymous pulls per source IP, and web sessions share
# a few egress IPs, so a boot without credentials fails with 429s. The stack
# only boots when both variables are set in the cloud environment's settings.
DOCKERHUB_USERNAME_VAR = "DOCKERHUB_USERNAME"
DOCKERHUB_TOKEN_VAR = "DOCKERHUB_TOKEN"
ES_MIN_MAP_COUNT = 262144
BOOT_TIMEOUT_SECONDS = 1200
DOCKERD_START_TIMEOUT_SECONDS = 60
# The longest one `--wait` call blocks, under the ten-minute cap on a tool
# call.
WAIT_SECONDS = 540
WAIT_POLL_SECONDS = 5


class Bail(Exception):
    """Stop the boot with a message for `--wait` to report."""


def log(message: str) -> None:
    """Print a line to the transcript, or to the boot log in the boot."""
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


def have_dockerhub_credentials() -> bool:
    """Whether the environment provides both Docker Hub credentials."""
    return bool(
        os.environ.get(DOCKERHUB_USERNAME_VAR)
        and os.environ.get(DOCKERHUB_TOKEN_VAR)
    )


def dockerhub_login() -> None:
    """Log the Docker daemon in to Docker Hub so pulls aren't rate-limited.

    The token goes in on stdin so it never appears in a process list or log.
    The login lands in ~/.docker/config.json, which is fine on an ephemeral
    session machine but must never be committed or copied elsewhere.
    """
    result = subprocess.run(
        [
            "docker",
            "login",
            "--username",
            os.environ[DOCKERHUB_USERNAME_VAR],
            "--password-stdin",
        ],
        input=os.environ[DOCKERHUB_TOKEN_VAR],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode != 0:
        # Docker's output echoes the registry's error, not the token.
        raise Bail(
            "Logging in to Docker Hub failed; check "
            f"{DOCKERHUB_USERNAME_VAR} and {DOCKERHUB_TOKEN_VAR}: "
            f"{result.stdout.strip()}"
        )


def show_credentials_note() -> None:
    """Explain why the stack isn't booting and how the user can enable it."""
    log("The development stack was NOT started: no Docker Hub credentials.")
    log("Docker Hub rate-limits anonymous pulls from shared cloud IPs, so")
    log("booting without a login usually fails with 429 Too Many Requests.")
    log("To enable the stack, the user must (never paste a token in chat):")
    log("  1. Create a Docker Hub access token with 'Public Repo Read-only'")
    log("     scope, ideally on a dedicated account.")
    log(
        "  2. In the cloud environment's settings (the environment menu in the"
    )
    log("     session's title bar, then Edit), set the variables")
    log(f"     {DOCKERHUB_USERNAME_VAR} and {DOCKERHUB_TOKEN_VAR}.")
    log("  3. Start a new session; it picks them up and boots the stack.")
    log("Tests can't run until then. Do not work around this: tell the user.")


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


def configure_environment(persist: bool) -> None:
    """Set the variables compose needs, and with `persist` keep them for the
    rest of the session rather than just this process."""
    variables = {
        # Makes `docker compose ...` use these files from anywhere.
        "COMPOSE_FILE": ":".join(str(p) for p in COMPOSE_FILES),
        "COMPOSE_PATH_SEPARATOR": ":",
        # The sandbox injects placeholder AWS variables for its own proxy.
        # The compose file passes them into the containers, where Django
        # would take them for real credentials, so blank them.
        "AWS_ACCESS_KEY_ID": "",
        "AWS_SECRET_ACCESS_KEY": "",
        "AWS_SESSION_TOKEN": "",
    }
    os.environ.update(variables)
    env_file = os.environ.get("CLAUDE_ENV_FILE")
    if not persist or not env_file:
        return
    with open(env_file, "a", encoding="utf-8") as f:
        for name, value in variables.items():
            f.write(f"export {name}={shlex.quote(value)}\n")


def build_proxy_ca_images() -> None:
    """Rebuild the stack's base images with the host's CA bundle installed,
    for the proxy-ca compose override to swap in. Does nothing when the host
    has no such bundle."""
    if not os.path.isfile(HOST_CA_BUNDLE):
        return
    stack_sources = "".join(
        path.read_text(encoding="utf-8")
        for path in (
            REPO / "docker" / "django" / "Dockerfile",
            COMPOSE_DIR / "docker-compose.yml",
        )
    )
    for base in PROXY_CA_IMAGES:
        if not re.search(
            rf"^\s*(FROM|image:) {re.escape(base)}(\s|$)", stack_sources, re.M
        ):
            raise Bail(
                f"The stack no longer uses the base image {base}; update"
                " PROXY_CA_IMAGES and proxy-ca/docker-compose.yml."
            )
    log("Rebuilding the stack's base images to trust the sandbox proxy...")
    context = STATE_DIR / "proxy-ca"
    context.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(HOST_CA_BUNDLE, context / "ca-bundle.crt")
    for base, tag in PROXY_CA_IMAGES.items():
        build = run(
            "docker",
            "build",
            "--quiet",
            "--build-arg",
            f"BASE={base}",
            "--tag",
            tag,
            "--file",
            str(PROXY_CA_DIR / "Dockerfile"),
            str(context),
            check=False,
        )
        if build.returncode:
            raise Bail(f"Building {tag} from {base} failed.")


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
    """Log container state and the tail of any stopped container's log."""
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


def start_stack() -> None:
    """Bring the stack up and wait until every healthcheck passes."""
    log("Starting the stack...")
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
    raise Bail("docker compose up did not bring the stack to a healthy state.")


def start_lint_sync() -> subprocess.Popen[str] | None:
    """Start installing the Python environment pre-commit and pyrefly run in.

    It runs alongside the stack's boot; finish_lint_sync collects it.
    """
    if shutil.which("uv") is None:
        return None
    log("Syncing the Python environment for pre-commit and pyrefly...")
    return subprocess.Popen(["uv", "sync", "--quiet"], text=True)


def finish_lint_sync(sync: subprocess.Popen[str] | None) -> str:
    """Wait for the lint tooling; return what is wrong with it, or ""."""
    if sync is None:
        return "uv is not installed, so linting on the host won't work."
    if sync.wait() == 0:
        hooks = run(
            "uv",
            "run",
            "--quiet",
            "pre-commit",
            "install-hooks",
            check=False,
            quiet=True,
        )
        if hooks.returncode == 0:
            return ""
    return (
        "uv sync failed, so linting on the host won't work until it is fixed."
    )


def write_status(state: str, detail: str = "", pid: int = 0) -> None:
    """Record the boot's state ("running", "ready" or "failed") for --wait."""
    status = {"state": state, "detail": detail, "pid": pid}
    BOOT_STATUS.write_text(json.dumps(status), encoding="utf-8")


def read_status() -> dict[str, str]:
    """The last recorded boot state, or {} if no boot has run."""
    try:
        return json.loads(BOOT_STATUS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def boot_running() -> bool:
    """Whether a background boot is still in progress."""
    status = read_status()
    if status.get("state") != "running":
        return False
    # The recorded pid can outlive its process across a resume, so check
    # that it is still this script's boot.
    try:
        cmdline = Path(f"/proc/{status.get('pid')}/cmdline").read_bytes()
    except OSError:
        return False
    return b"--boot" in cmdline


def start_boot() -> None:
    """Start a background boot unless one is already in progress."""
    if boot_running():
        return
    with BOOT_LOG.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            [sys.executable, str(SELF), "--boot"],
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    # The boot only writes its final state, which takes it at least a
    # Docker round trip to reach, so this can't overwrite it.
    write_status("running", pid=process.pid)


def boot() -> None:
    """Bring up the stack and the lint tooling; runs detached by start_boot."""
    lint = start_lint_sync()
    try:
        start_dockerd()
        dockerhub_login()
        build_proxy_ca_images()
        ensure_max_map_count()
        ensure_env_file()
        current_hash = image_inputs_hash()
        rebuild_if_dependencies_changed(current_hash)
        start_stack()
        IMAGE_STAMP.write_text(current_hash, encoding="utf-8")
    except Bail as problem:
        finish_lint_sync(lint)
        write_status("failed", str(problem))
        return
    except Exception as error:
        traceback.print_exc()
        write_status("failed", f"The boot crashed: {error!r}")
        return
    write_status("ready", finish_lint_sync(lint))
    log("Ready.")


def show_log_tail(lines: int) -> None:
    """Print the end of the boot log."""
    try:
        text = BOOT_LOG.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    # Docker's build output is padded with blank lines; skip them.
    tail = [line for line in text.splitlines() if line.strip()][-lines:]
    for line in tail:
        print(f"    {line}", flush=True)


def show_hints() -> None:
    """Explain the usual reasons a boot fails."""
    log("Hints:")
    log("  * A download refused with 403 or Forbidden is this environment's")
    log("    network policy, which nothing inside the session can change.")
    log("    Tell the user which host was refused; they allow it in the")
    log("    environment's network access settings. A first boot needs:")
    log(f"    {', '.join(DOWNLOAD_HOSTS)}")
    log("  * A certificate error inside a build or container (UnknownIssuer,")
    log("    SELF_SIGNED_CERT_IN_CHAIN) means it did not get the host's CA")
    log("    bundle; check that SSL_CERT_FILE points at an existing file.")
    log("  * 429 Too Many Requests from Docker Hub means the login was not")
    log("    applied or the account itself is rate-limited; retry later.")
    log("  * Elasticsearch needs about 1 GB of memory.")
    log(f"  * Full log: {BOOT_LOG}")


def wait_for_stack() -> int:
    """Start a boot if none is running and wait for it; return an exit code."""
    start_boot()
    deadline = time.monotonic() + WAIT_SECONDS
    next_note = time.monotonic() + 60
    while boot_running():
        if time.monotonic() >= deadline:
            log(
                f"Still starting after {WAIT_SECONDS // 60} minutes. Run "
                f"`{WAIT_COMMAND}` again to keep waiting. Latest log lines:"
            )
            show_log_tail(10)
            return 2
        if time.monotonic() >= next_note:
            log("Still starting...")
            next_note += 60
        time.sleep(WAIT_POLL_SECONDS)
    status = read_status()
    if status.get("state") != "ready":
        detail = status.get("detail") or "The boot stopped without a reason."
        log(f"PROBLEM: {detail} Latest log lines:")
        show_log_tail(40)
        show_hints()
        log(f"To retry once the cause is fixed, run `{WAIT_COMMAND}`.")
        return 1
    log("The stack is up.")
    if detail := status.get("detail"):
        log(detail)
    log("  Site:   http://localhost:8000")
    log("  Tests:  docker exec cl-django ./manage.py test cl.<app> --keepdb")
    log("  Lint:   uv run pre-commit run --files <changed files>")
    log(
        "  Stack:  docker compose ps | logs -f cl-django | exec cl-django bash"
    )
    return 0


def main() -> int:
    """Dispatch: the hook (no argument), --wait for the agent, --boot."""
    if os.environ.get("CLAUDE_CODE_REMOTE") != "true":
        if "--wait" in sys.argv:
            print(
                "Not a Claude Code web session; use `docker compose up --wait`."
            )
        return 0
    os.chdir(REPO)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if not have_dockerhub_credentials():
        if "--boot" not in sys.argv:
            show_credentials_note()
        return 1 if "--wait" in sys.argv else 0
    if "--boot" in sys.argv:
        configure_environment(persist=False)
        boot()
        return 0
    if "--wait" in sys.argv:
        configure_environment(persist=False)
        return wait_for_stack()
    configure_environment(persist=True)
    start_boot()
    log(f"Booting the development stack in the background (log: {BOOT_LOG}).")
    log("A new session starts on a fresh machine, so the first boot pulls the")
    log(
        "service images and builds the Django image, which takes 10-20 minutes."
    )
    log("A resumed session is ready in seconds.")
    log(f"Before running tests, wait for it with: {WAIT_COMMAND}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
