"""GitLab REST API v4 client."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings
from app.services.errors import ApiError

logger = logging.getLogger(__name__)


class GitLabClient:
    """Async wrapper around the GitLab REST API v4."""

    def __init__(self) -> None:
        settings = get_settings()
        self._base = f"{settings.gitlab_url}/api/v4"
        self._base_url = settings.gitlab_url
        self._token = settings.gitlab_token
        self._timeout = settings.request_timeout
        self._verify = settings.ssl_verify
        self._target_group = settings.gitlab_target_group
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base,
                headers={"PRIVATE-TOKEN": self._token},
                timeout=self._timeout,
                verify=self._verify,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    async def _call(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Wrapper that enriches httpx errors with full request/response context."""
        full_url = f"{self._base_url}/api/v4{path}"
        try:
            if method == "GET":
                resp = await self.client.get(path, **kwargs)
            else:
                raise ValueError(f"Unsupported method: {method}")
            return resp
        except ApiError:
            raise
        except httpx.HTTPStatusError as exc:
            raise ApiError.from_httpx(exc, method, full_url) from exc
        except httpx.RequestError as exc:
            raise ApiError.from_httpx(exc, method, full_url) from exc

    async def _paginate(self, path: str, **params: Any) -> list[dict[str, Any]]:
        """Fetch all pages for a GET endpoint that returns a JSON array."""
        items: list[dict[str, Any]] = []
        page = 1
        while True:
            resp = await self._call(
                "GET", path, params={**params, "per_page": 100, "page": page}
            )
            resp.raise_for_status()
            body = resp.json()
            if not body:
                break
            items.extend(body)
            if len(body) < 100:
                break
            page += 1
        return items

    # ------------------------------------------------------------------
    # connectivity
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        """Return True if the GitLab API is reachable and the token is valid."""
        try:
            await self._call("GET", "/version")
            return True
        except ApiError:
            logger.exception("GitLab health-check failed")
            return False

    # ------------------------------------------------------------------
    # group resolution
    # ------------------------------------------------------------------

    async def _resolve_group_id(self, group_ref: str) -> int:
        """Resolve a group ID or URL-encoded path to a numeric group ID."""
        if group_ref.isdigit():
            return int(group_ref)
        encoded = group_ref.replace("/", "%2F")
        resp = await self._call("GET", f"/groups/{encoded}")
        resp.raise_for_status()
        return resp.json()["id"]

    # ------------------------------------------------------------------
    # recursive discovery
    # ------------------------------------------------------------------

    async def discover_projects(self) -> list[dict[str, Any]]:
        """Return every non-archived project under *target_group* and its sub-groups.

        Each dict contains at minimum:
          * id
          * name
          * path_with_namespace
          * http_url_to_repo
          * ssh_url_to_repo
        """
        group_id = await self._resolve_group_id(self._target_group)
        logger.info("Discovering projects under GitLab group id=%d", group_id)
        projects = await self._paginate(
            f"/groups/{group_id}/projects",
            include_subgroups="true",
            archived="false",
            with_shared="false",
        )
        logger.info("Discovered %d GitLab project(s)", len(projects))
        return projects