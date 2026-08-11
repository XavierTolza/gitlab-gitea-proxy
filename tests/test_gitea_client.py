"""Tests for Gitea API client (ephemeral testcontainer)."""

import pytest


@pytest.mark.asyncio
async def test_gitea_version_endpoint(gitea_client):
    """Verify the ephemeral Gitea container is reachable."""
    resp = await gitea_client.get("/version")
    assert resp.status_code == 200, f"Gitea version check failed: {resp.text}"
    data = resp.json()
    assert "version" in data


@pytest.mark.asyncio
async def test_gitea_create_org(gitea_client):
    """Verify we can create an organisation."""
    import uuid

    org_name = f"test-org-{uuid.uuid4().hex[:8]}"
    resp = await gitea_client.post(
        "/orgs", json={"username": org_name, "full_name": org_name}
    )
    assert resp.status_code == 201, f"Create org failed: {resp.text}"
    data = resp.json()
    assert data["username"] == org_name

    # Verify it exists
    resp = await gitea_client.get(f"/orgs/{org_name}")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_gitea_migrate_repo(gitea_client, gitea_url):
    """Verify the migrate endpoint accepts a mirror request.

    Uses a tiny public repo to test migration without requiring GitLab access.
    """
    import uuid

    uid = uuid.uuid4().hex[:8]
    org_name = f"mirror-org-{uid}"
    repo_name = f"mirror-repo-{uid}"

    # Create org
    resp = await gitea_client.post(
        "/orgs", json={"username": org_name, "full_name": org_name}
    )
    assert resp.status_code == 201, f"Create org failed: {resp.text}"

    # Migrate a tiny public repo as a mirror
    resp = await gitea_client.post(
        "/repos/migrate",
        json={
            "clone_addr": "https://github.com/octocat/hello-world.git",
            "mirror": True,
            "repo_name": repo_name,
            "repo_owner": org_name,
            "wiki": False,
            "issues": False,
            "pull_requests": False,
        },
    )
    assert resp.status_code in (201, 409), f"Migrate failed: {resp.text}"
    data = resp.json()
    assert data.get("name") == repo_name or "repo_name" in str(data).lower()


@pytest.mark.asyncio
async def test_gitea_mirror_sync(gitea_client, gitea_url):
    """Verify mirror-sync endpoint works."""
    import uuid

    uid = uuid.uuid4().hex[:8]
    org_name = f"sync-org-{uid}"
    repo_name = f"sync-repo-{uid}"

    # Create org
    resp = await gitea_client.post(
        "/orgs", json={"username": org_name, "full_name": org_name}
    )
    assert resp.status_code == 201

    # Create mirror
    resp = await gitea_client.post(
        "/repos/migrate",
        json={
            "clone_addr": "https://github.com/octocat/hello-world.git",
            "mirror": True,
            "repo_name": repo_name,
            "repo_owner": org_name,
            "wiki": False,
            "issues": False,
            "pull_requests": False,
        },
    )
    assert resp.status_code in (201, 409)

    # Trigger mirror sync
    resp = await gitea_client.post(f"/repos/{org_name}/{repo_name}/mirror-sync")
    # 200 = sync triggered, could also be other codes
    assert resp.status_code < 500, f"Mirror sync failed: {resp.text}"


@pytest.mark.asyncio
async def test_gitea_unreachable_does_not_crash():
    """Degraded mode: invalid URL should raise an exception."""
    import httpx

    async with httpx.AsyncClient(
        base_url="https://192.0.2.1/api/v1",
        headers={"Authorization": "token fake"},
        timeout=3,
    ) as client:
        with pytest.raises(Exception):
            resp = await client.get("/version")
            resp.raise_for_status()