"""Docker smoke check for the admin BFF path.

The script starts backend/frontend with temporary admin credentials, logs in
through the Next.js server, calls a protected proxied backend route, and verifies
the temporary admin key is not present in the built frontend files.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_URL = os.environ.get("SMOKE_FRONTEND_URL", "http://localhost:3000")
BACKEND_URL = os.environ.get("SMOKE_BACKEND_URL", "http://localhost:8000")
ADMIN_KEY = os.environ.get("ADMIN_API_KEY") or "test-admin-key-for-smoke"
SESSION_SECRET = (
    os.environ.get("ADMIN_SESSION_SECRET")
    or f"smoke-session-{secrets.token_urlsafe(24)}"
)
COMPOSE_CONTAINER_NAMES = {"research-agent-backend", "research-agent-frontend"}


def run(command: list[str], env: dict[str, str]) -> None:
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def existing_container_names(env: dict[str, str]) -> set[str]:
    result = subprocess.run(
        ["docker", "ps", "-a", "--format", "{{.Names}}"],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def assert_compose_names_available(env: dict[str, str]) -> None:
    if env.get("SMOKE_ALLOW_CONTAINER_RECREATE") == "1":
        return
    conflicts = COMPOSE_CONTAINER_NAMES & existing_container_names(env)
    if conflicts:
        names = ", ".join(sorted(conflicts))
        raise RuntimeError(
            "Smoke compose container names are already in use: "
            f"{names}. Stop them first or set SMOKE_ALLOW_CONTAINER_RECREATE=1."
        )


def wait_for_url(url: str, *, timeout_seconds: int = 90) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                if 200 <= response.status < 500:
                    return
        except Exception as exc:  # noqa: BLE001 - report the last connection error.
            last_error = exc
        time.sleep(2)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


def main() -> int:
    env = os.environ.copy()
    env["ADMIN_API_KEY"] = ADMIN_KEY
    env["ADMIN_SESSION_SECRET"] = SESSION_SECRET
    env.setdefault("APP_ENV", "production")

    assert_compose_names_available(env)
    run(["docker", "compose", "up", "-d", "--build", "backend", "frontend"], env)
    wait_for_url(f"{BACKEND_URL}/health")
    wait_for_url(f"{FRONTEND_URL}/api/admin/session")

    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(CookieJar())
    )
    login_request = urllib.request.Request(
        f"{FRONTEND_URL}/api/admin/login",
        data=json.dumps({"adminKey": ADMIN_KEY}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with opener.open(login_request, timeout=10) as response:
        if response.status != 200:
            raise RuntimeError(f"Admin login failed with status {response.status}")

    with opener.open(f"{FRONTEND_URL}/api/backend/api/config", timeout=10) as response:
        if response.status != 200:
            raise RuntimeError(
                f"Protected proxy check failed with status {response.status}"
            )

    grep_command = (
        'if grep -R "$ADMIN_API_KEY" /app/.next /app/public /app/server.js '
        "2>/dev/null; then exit 1; fi"
    )
    run(["docker", "compose", "exec", "-T", "frontend", "sh", "-lc", grep_command], env)
    print("Admin BFF smoke check passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.CalledProcessError, urllib.error.URLError) as exc:
        print(f"Admin BFF smoke check failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
