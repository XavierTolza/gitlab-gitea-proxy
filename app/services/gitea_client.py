"""Gitea REST API v1 client."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class GiteaClient:
    """Async wrapper around the Gitea REST API v1."""

    def __init__(self) -> None:
        settings = get_settings()
        self._base = f"{settings.gitea_url}/api/v1"
        self._token = settings.gitea_token
        self._timeout = settings.request_timeout
        self._target_org = settings.gitea_target_org
        self._gitlab_url = settings.gitlab_url
        self._gitlab_token = settings.gitlab_token
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base,
                headers={"Authorization": f"token {self._token}"},
                timeout=self._timeout,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # connectivity
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        """Return True if the Gitea API is reachable and the token is valid."""
        try:
            resp = await self.client.get("/version")
            resp.raise_for_status()
            return True
        except Exception:
            logger.exception("Gitea health-check failed")
            return False

    # ------------------------------------------------------------------
    # organisations
    # ------------------------------------------------------------------

    async def ensure_org(self, org_name: str) -> None:
        """Create the organisation *org_name* if it does not already exist."""
        resp = await self.client.get(f"/orgs/{org_name}")
        if resp.status_code == 200:
            logger.debug("Gitea org '%s' already exists", org_name)
            return
        logger.info("Creating Gitea org '%s'", org_name)
        resp = await self.client.post(
            "/orgs", json={"username": org_name, "full_name": org_name}
        )
        if resp.status_code == 422:  # already exists (race)
            logger.debug("Gitea org '%s' already exists (422)", org_name)
            return
        resp.raise_for_status()

    # ------------------------------------------------------------------
    # mirror repository
    # ------------------------------------------------------------------

    async def repo_exists(self, owner: str, repo: str) -> bool:
        resp = await self.client.get(f"/repos/{owner}/{repo}")
        return resp.status_code == 200

    async def create_mirror(
        self, owner: str, repo_name: str, clone_url: str, description: str = ""
    ) -> dict[str, Any]:
        """Create a mirrored repository on Gitea via the migrate endpoint.

        Returns the JSON representation of the newly created repository.
        """
        payload: dict[str, Any] = {
            "clone_addr": clone_url,
            "auth_token": self._gitlab_token,
            "mirror": True,
            "repo_name": repo_name,
            "repo_owner": owner,
            "service": "gitlab",
            "wiki": False,
            "issues": False,
            "pull_requests": False,
            "milestones": False,
            "labels": False,
            "releases": False,
        }
        if description:
            payload["description"] = description

        logger.info(
            "Creating mirror repo '%s/%s' from %s",
            owner,
            repo_name,
            clone_url,
        )
        resp = await self.client.post("/repos/migrate", json=payload)
        if resp.status_code == 409:
            body = resp.json()
            logger.info("Mirror already exists: %s", body.get("html_url", "?"))
            return body
        resp.raise_for_status()
        return resp.json()

    async def trigger_mirror_sync(self, owner: str, repo: str) -> bool:
        """Manually trigger a mirror sync. Returns True on success."""
        resp = await self.client.post(f"/repos/{owner}/{repo}/mirror-sync")
        if resp.status_code == 200:
            logger.info("Mirror sync triggered for %s/%s", owner, repo)
            return True
        logger.warning(
            "Mirror sync for %s/%s returned %d: %s",
            owner,
            repo,
            resp.status_code,
            resp.text,
        )
        return False

    async def get_repo(self, owner: str, repo: str) -> dict[str, Any]:
        resp = await self.client.get(f"/repos/{owner}/{repo}")
        resp.raise_for_status()
        return resp.json()