"""Tests for GitLab API client (real API)."""

import pytest


@pytest.mark.asyncio
async def test_gitlab_version_endpoint(gitlab_client):
    """Verify the GitLab API is reachable with the provided token."""
    resp = await gitlab_client.get("/version")
    assert resp.status_code == 200, f"GitLab version check failed: {resp.text}"
    data = resp.json()
    assert "version" in data


@pytest.mark.asyncio
async def test_gitlab_list_projects(gitlab_client, gitlab_test_group):
    """Verify we can list projects in a test group."""
    if not gitlab_test_group:
        pytest.skip("TEST_GITLAB_TARGET_GROUP not set")

    # Resolve group
    if gitlab_test_group.isdigit():
        group_id = gitlab_test_group
    else:
        encoded = gitlab_test_group.replace("/", "%2F")
        resp = await gitlab_client.get(f"/groups/{encoded}")
        assert resp.status_code == 200, f"Group resolution failed: {resp.text}"
        group_id = resp.json()["id"]

    resp = await gitlab_client.get(
        f"/groups/{group_id}/projects",
        params={
            "include_subgroups": "true",
            "archived": "false",
            "with_shared": "false",
            "per_page": 5,
            "page": 1,
        },
    )
    assert resp.status_code == 200, f"List projects failed: {resp.text}"
    projects = resp.json()
    assert isinstance(projects, list)


@pytest.mark.asyncio
async def test_gitlab_unreachable_does_not_crash():
    """Degraded mode: invalid URL should raise an exception, not hang."""
    import httpx

    async with httpx.AsyncClient(
        base_url="https://192.0.2.1/api/v4",
        headers={"PRIVATE-TOKEN": "fake"},
        timeout=3,
    ) as client:
        with pytest.raises(Exception):
            resp = await client.get("/version")
            resp.raise_for_status()