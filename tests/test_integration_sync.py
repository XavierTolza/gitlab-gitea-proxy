"""End-to-end integration tests: GitLab discovery → Gitea mirror provisioning."""

from __future__ import annotations

import uuid

import pytest


@pytest.mark.asyncio
async def test_full_sync_pipeline(
    gitlab_client,
    gitlab_test_token,
    gitlab_test_url,
    gitlab_test_group,
    gitea_client,
    gitea_url,
):
    """End-to-end: discover a GitLab group and mirror its repos to Gitea."""
    if not gitlab_test_group:
        pytest.skip("TEST_GITLAB_TARGET_GROUP not set")

    # 1. Discover projects from GitLab
    if gitlab_test_group.isdigit():
        group_id = gitlab_test_group
    else:
        encoded = gitlab_test_group.replace("/", "%2F")
        resp = await gitlab_client.get(f"/groups/{encoded}")
        assert resp.status_code == 200, f"Cannot resolve group: {resp.text}"
        group_id = resp.json()["id"]

    resp = await gitlab_client.get(
        f"/groups/{group_id}/projects",
        params={
            "include_subgroups": "true",
            "archived": "false",
            "with_shared": "false",
            "per_page": 100,
            "page": 1,
        },
    )
    assert resp.status_code == 200, f"Cannot list projects: {resp.text}"
    projects = resp.json()

    if not projects:
        pytest.skip("No projects found in the test group — nothing to mirror")

    # 2. Create a test org on Gitea for mirrors
    uid = uuid.uuid4().hex[:8]
    org_name = f"gitlab-mirror-{uid}"
    resp = await gitea_client.post(
        "/orgs", json={"username": org_name, "full_name": org_name}
    )
    assert resp.status_code == 201, f"Cannot create Gitea org: {resp.text}"

    # 3. Mirror the first project
    proj = projects[0]
    repo_name = proj["name"].lower().replace(" ", "-")
    clone_url = proj["http_url_to_repo"]

    # Build authenticated clone URL for Gitea to pull from
    if "://" in clone_url:
        scheme, rest = clone_url.split("://", 1)
        auth_clone_url = f"{scheme}://oauth2:{gitlab_test_token}@{rest}"
    else:
        auth_clone_url = clone_url

    resp = await gitea_client.post(
        "/repos/migrate",
        json={
            "clone_addr": auth_clone_url,
            "mirror": True,
            "repo_name": repo_name,
            "repo_owner": org_name,
            "service": "gitlab",
            "wiki": False,
            "issues": False,
            "pull_requests": False,
            "milestones": False,
            "labels": False,
            "releases": False,
        },
    )
    assert resp.status_code in (201, 409), f"Migrate failed: {resp.text}"
    data = resp.json()

    # 4. Verify the mirror exists on Gitea
    resp = await gitea_client.get(f"/repos/{org_name}/{repo_name}")
    assert resp.status_code == 200, f"Repo not found after migration: {resp.text}"
    repo_data = resp.json()
    assert repo_data["name"] == repo_name
    assert repo_data.get("mirror", False) is True

    # 5. Trigger a mirror sync
    resp = await gitea_client.post(f"/repos/{org_name}/{repo_name}/mirror-sync")
    assert resp.status_code < 500, f"Mirror sync trigger failed: {resp.text}"