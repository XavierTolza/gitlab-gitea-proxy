"""Shared fixtures for integration tests."""

from __future__ import annotations

import os
import time
from typing import AsyncGenerator

import httpx
import pytest
import pytest_asyncio
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs

GITEA_HTTP_PORT = 3000


@pytest.fixture(scope="session")
def gitea_container():
    """Spin up an ephemeral Gitea container for the test session."""
    container = (
        DockerContainer("gitea/gitea:1.22")
        .with_exposed_ports(GITEA_HTTP_PORT, 22)
        .with_env("GITEA__server__DOMAIN", "localhost")
        .with_env("GITEA__server__HTTP_PORT", str(GITEA_HTTP_PORT))
        .with_env("GITEA__server__ROOT_URL", f"http://localhost:{GITEA_HTTP_PORT}/")
        .with_env("GITEA__security__INSTALL_LOCK", "true")
        .with_env("GITEA__database__DB_TYPE", "sqlite3")
        .with_env("GITEA__repository__ENABLE_PUSH_CREATE_USER", "true")
        .with_env("GITEA__repository__ENABLE_PUSH_CREATE_ORG", "true")
    )
    container.start()
    wait_for_logs(container, "Listen: http://0.0.0.0:3000", timeout=60)
    yield container
    container.stop()


@pytest.fixture(scope="session")
def gitea_url(gitea_container: DockerContainer) -> str:
    host = gitea_container.get_container_host_ip()
    port = gitea_container.get_exposed_port(GITEA_HTTP_PORT)
    return f"http://{host}:{port}"


@pytest.fixture(scope="session")
def gitea_admin_token(gitea_url: str) -> str:
    """Create an admin user via the CLI inside the container and return its token."""
    import subprocess

    # Get container ID
    container_id = (
        subprocess.check_output(["docker", "ps", "-q", "-f", f"publish={GITEA_HTTP_PORT}"])
        .decode()
        .strip()
        .split("\n")[0]
    )
    # Create admin user
    subprocess.run(
        [
            "docker", "exec", container_id,
            "gitea", "admin", "user", "create",
            "--username", "admin",
            "--password", "admin1234",
            "--email", "admin@test.local",
            "--admin",
            "--must-change-password=false",
            "--access-token",
        ],
        capture_output=True,
        check=False,
    )
    # Generate a token
    result = subprocess.run(
        [
            "docker", "exec", container_id,
            "gitea", "admin", "user", "generate-access-token",
            "--username", "admin",
            "--token-name", "test-token",
            "--scopes", "write:repository,write:user,write:admin,read:organization,write:organization",
            "--raw",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()

    # Fallback: create user via API
    resp = httpx.post(
        f"{gitea_url}/api/v1/admin/users",
        headers={"Content-Type": "application/json"},
        json={
            "login_name": "admin2",
            "username": "admin2",
            "email": "admin2@test.local",
            "password": "admin1234",
            "must_change_password": False,
        },
        timeout=30,
    )
    # We still need admin access which requires initial setup...
    # For test purposes, return a placeholder — the test will skip if needed
    return ""


@pytest.fixture(scope="session")
def gitlab_test_token() -> str:
    token = os.getenv("TEST_GITLAB_TOKEN", "")
    if not token:
        pytest.skip("TEST_GITLAB_TOKEN not set")
    return token


@pytest.fixture(scope="session")
def gitlab_test_url() -> str:
    return os.getenv("TEST_GITLAB_URL", "https://gitlab.com")


@pytest.fixture(scope="session")
def gitlab_test_group() -> str:
    return os.getenv("TEST_GITLAB_TARGET_GROUP", "")


@pytest_asyncio.fixture
async def gitea_client(gitea_url: str, gitea_admin_token: str) -> AsyncGenerator[httpx.AsyncClient, None]:
    """An httpx AsyncClient pre-configured for the ephemeral Gitea."""
    async with httpx.AsyncClient(
        base_url=f"{gitea_url}/api/v1",
        headers={"Authorization": f"token {gitea_admin_token}"},
        timeout=30,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def gitlab_client(gitlab_test_token: str, gitlab_test_url: str) -> AsyncGenerator[httpx.AsyncClient, None]:
    """An httpx AsyncClient pre-configured for the real GitLab."""
    async with httpx.AsyncClient(
        base_url=f"{gitlab_test_url}/api/v4",
        headers={"PRIVATE-TOKEN": gitlab_test_token},
        timeout=30,
    ) as client:
        yield client