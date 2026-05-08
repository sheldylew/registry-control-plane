import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.phase4_seed import READER_PASSWORD, REVOKED_ROBOT_TOKEN, ROBOT_NAME, ROBOT_TOKEN

BASE_URL = "http://localhost:8080"
SERVICE = "sheldylew-registry"
LOCAL_COMPOSE = ["docker", "compose", "-f", "docker-compose.yml", "-f", "docker-compose.local.yml"]
FIXTURE_IMAGE = "localhost:8080/sheldylew/fixture:phase4"
DEVELOPER_OK_IMAGE = "localhost:8080/sheldylew/developer-ok:phase4"
DEVELOPER_DENIED_IMAGE = "localhost:8080/otherns/developer-denied:phase4"
READER_DENIED_IMAGE = "localhost:8080/sheldylew/reader-denied:phase4"
ROBOT_OK_IMAGE = "localhost:8080/sheldylew/sheldylew.com:phase4"


def run(
    cmd: List[str],
    *,
    check: bool = True,
    input_text: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=ROOT,
        input=input_text,
        text=True,
        capture_output=True,
        check=check,
        env=env,
    )


def wait_for_http(url: str, expected_code: int = 200, timeout_seconds: int = 30) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        response = run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", url], check=False)
        if response.stdout.strip() == str(expected_code):
            return
        time.sleep(1)
    raise AssertionError(f"Timed out waiting for {url} to return {expected_code}.")


def assert_failure(result: subprocess.CompletedProcess[str]) -> None:
    combined = f"{result.stdout}\n{result.stderr}".lower()
    assert result.returncode != 0, combined
    assert any(marker in combined for marker in ["denied", "unauthorized", "insufficient_scope"]), combined


def docker_logout() -> None:
    run(["docker", "logout", "localhost:8080"], check=False)


def docker_login(username: str, secret: str) -> subprocess.CompletedProcess[str]:
    docker_logout()
    return run(
        ["docker", "login", "localhost:8080", "--username", username, "--password-stdin"],
        check=False,
        input_text=secret,
    )


def ensure_local_image(tag: str) -> None:
    run(["docker", "build", "-t", tag, "./smoke"])


@pytest.fixture(scope="module")
def seeded_stack() -> None:
    try:
        run(["docker", "info"])
    except FileNotFoundError as exc:
        pytest.skip(f"Docker is required: {exc}")

    env = os.environ | {
        "ADMIN_USERNAME": "admin",
        "ADMIN_PASSWORD": "change-me-now",
        "ADMIN_EMAIL": "admin@example.com",
    }

    run([*LOCAL_COMPOSE, "up", "--build", "-d", "--force-recreate"], env=env)
    wait_for_http(f"{BASE_URL}/healthz")
    run([*LOCAL_COMPOSE, "exec", "-T", "api", "python", "-m", "backend.phase4_seed"], env=env)

    ensure_local_image(FIXTURE_IMAGE)
    login = docker_login("admin", env["ADMIN_PASSWORD"])
    assert login.returncode == 0, f"{login.stdout}\n{login.stderr}"
    run(["docker", "push", FIXTURE_IMAGE])


def test_reader_can_login_and_pull_allowed_repo(seeded_stack) -> None:
    run(["docker", "image", "rm", FIXTURE_IMAGE], check=False)

    login = docker_login("reader", READER_PASSWORD)
    assert login.returncode == 0, f"{login.stdout}\n{login.stderr}"

    pull = run(["docker", "pull", FIXTURE_IMAGE], check=False)
    assert pull.returncode == 0, f"{pull.stdout}\n{pull.stderr}"


def test_reader_cannot_push_allowed_repo(seeded_stack) -> None:
    ensure_local_image(READER_DENIED_IMAGE)

    login = docker_login("reader", READER_PASSWORD)
    assert login.returncode == 0, f"{login.stdout}\n{login.stderr}"

    push = run(["docker", "push", READER_DENIED_IMAGE], check=False)
    assert_failure(push)


def test_developer_can_push_allowed_namespace(seeded_stack) -> None:
    ensure_local_image(DEVELOPER_OK_IMAGE)

    login = docker_login("developer", "developer-pass-123")
    assert login.returncode == 0, f"{login.stdout}\n{login.stderr}"

    push = run(["docker", "push", DEVELOPER_OK_IMAGE], check=False)
    assert push.returncode == 0, f"{push.stdout}\n{push.stderr}"


def test_developer_cannot_push_other_namespace(seeded_stack) -> None:
    ensure_local_image(DEVELOPER_DENIED_IMAGE)

    login = docker_login("developer", "developer-pass-123")
    assert login.returncode == 0, f"{login.stdout}\n{login.stderr}"

    push = run(["docker", "push", DEVELOPER_DENIED_IMAGE], check=False)
    assert_failure(push)


def test_robot_can_push_exact_allowed_repo(seeded_stack) -> None:
    ensure_local_image(ROBOT_OK_IMAGE)

    login = docker_login(ROBOT_NAME, ROBOT_TOKEN)
    assert login.returncode == 0, f"{login.stdout}\n{login.stderr}"

    push = run(["docker", "push", ROBOT_OK_IMAGE], check=False)
    assert push.returncode == 0, f"{push.stdout}\n{push.stderr}"


def test_revoked_robot_token_fails_login(seeded_stack) -> None:
    login = docker_login(ROBOT_NAME, REVOKED_ROBOT_TOKEN)
    combined = f"{login.stdout}\n{login.stderr}".lower()

    assert login.returncode != 0, combined
    assert "unauthorized" in combined or "denied" in combined, combined
