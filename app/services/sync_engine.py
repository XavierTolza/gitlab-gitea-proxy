"""Sync engine — orchestrates discovery + mirroring, holds in-memory state."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.config import get_settings
from app.services.errors import ApiError
from app.services.gitlab_client import GitLabClient
from app.services.gitea_client import GiteaClient

logger = logging.getLogger(__name__)


class MirrorStatus(str, Enum):
    OK = "ok"
    ERROR = "error"
    SYNCING = "syncing"


class ServiceHealth(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    AUTH_ERROR = "auth_error"


@dataclass
class ProjectMirror:
    gl_id: int
    gl_name: str
    gl_path: str
    gl_http_url: str
    gitea_org: str
    gitea_repo: str
    gitea_url: str
    status: MirrorStatus = MirrorStatus.OK
    last_success: datetime | None = None
    error_message: str = ""
    error_detail: dict[str, Any] | None = None


@dataclass
class SystemState:
    gitlab_health: ServiceHealth = ServiceHealth.OFFLINE
    gitea_health: ServiceHealth = ServiceHealth.OFFLINE
    last_full_scan: datetime | None = None
    last_scan_error: str | None = None
    projects: dict[str, ProjectMirror] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)


# global singleton
_state = SystemState()


def get_state() -> SystemState:
    return _state


async def _path_to_gitea(
    path_with_namespace: str, root_org: str, gitlab_root: str
) -> tuple[str, str]:
    """Convert GitLab 'groupe/sous-groupe/projet' → Gitea (org, repo_name)."""
    parts = path_with_namespace.rsplit("/", 1)
    if len(parts) == 1:
        return root_org, parts[0]
    sub_path, repo = parts
    # Mirror the subgroup tree as Gitea orgs: root_org becomes the root,
    # then each sub-group becomes an org prefix, and the repo sits in the
    # closest parent org.
    # E.g.  mon-equipe/projets → org=root_org-projets, repo=projet
    #       mon-equipe/projets/a/b → org=root_org-a-b, repo=repo_name
    org = sub_path.replace(gitlab_root, root_org).replace("/", "-")
    return org, repo


async def run_full_sync() -> None:
    """Discover all GitLab projects and ensure mirrors exist on Gitea."""
    state = get_state()
    async with state._lock:
        state.last_full_scan = datetime.now(timezone.utc)
        state.last_scan_error = None

    gl = GitLabClient()
    ge = GiteaClient()
    settings = get_settings()

    try:
        # Health checks
        gl_ok = await gl.health_check()
        ge_ok = await ge.health_check()
        async with state._lock:
            state.gitlab_health = (
                ServiceHealth.ONLINE if gl_ok else ServiceHealth.OFFLINE
            )
            state.gitea_health = (
                ServiceHealth.ONLINE if ge_ok else ServiceHealth.OFFLINE
            )

        if not gl_ok:
            msg = "GitLab is unreachable – skipping scan"
            logger.warning(msg)
            async with state._lock:
                state.last_scan_error = msg
            return

        if not ge_ok:
            msg = "Gitea is unreachable – cannot provision mirrors"
            logger.warning(msg)
            async with state._lock:
                state.last_scan_error = msg
            return

        # Discovery
        projects = await gl.discover_projects()
        logger.info("Processing %d project(s)", len(projects))

        # Ensure root org
        await ge.ensure_org(settings.gitea_target_org)

        for proj in projects:
            gl_path = proj["path_with_namespace"]
            gl_http = proj["http_url_to_repo"]
            gl_id = proj["id"]
            gl_name = proj["name"]

            org, repo = await _path_to_gitea(
                gl_path, settings.gitea_target_org, settings.gitlab_target_group
            )
            key = f"{org}/{repo}"

            # Update state
            async with state._lock:
                if key not in state.projects:
                    state.projects[key] = ProjectMirror(
                        gl_id=gl_id,
                        gl_name=gl_name,
                        gl_path=gl_path,
                        gl_http_url=gl_http,
                        gitea_org=org,
                        gitea_repo=repo,
                        gitea_url=f"{settings.gitea_url}/{org}/{repo}",
                    )
                mirror = state.projects[key]
                mirror.status = MirrorStatus.SYNCING

            try:
                await ge.ensure_org(org)
                if not await ge.repo_exists(org, repo):
                    await ge.create_mirror(
                        owner=org,
                        repo_name=repo,
                        clone_url=gl_http,
                        description=f"Mirror of {gl_path} from GitLab",
                    )
                    mirror.last_success = datetime.now(timezone.utc)
                else:
                    # repo already exists – optionally trigger sync
                    await ge.trigger_mirror_sync(org, repo)
                    mirror.last_success = datetime.now(timezone.utc)

                async with state._lock:
                    mirror.status = MirrorStatus.OK
                    mirror.error_message = ""

            except ApiError as exc:
                logger.error("API error mirroring %s: %s", gl_path, exc)
                async with state._lock:
                    mirror.status = MirrorStatus.ERROR
                    mirror.error_message = str(exc)
                    mirror.error_detail = exc.to_dict()
            except Exception as exc:
                logger.exception("Failed to mirror %s", gl_path)
                async with state._lock:
                    mirror.status = MirrorStatus.ERROR
                    mirror.error_message = str(exc)
                    mirror.error_detail = None

    except Exception as exc:
        logger.exception("Full sync failed")
        async with state._lock:
            state.last_scan_error = str(exc)
    finally:
        await gl.close()
        await ge.close()


async def sync_single_project(org: str, repo: str) -> None:
    """Trigger mirror sync for a single project."""
    ge = GiteaClient()
    try:
        ok = await ge.trigger_mirror_sync(org, repo)
        state = get_state()
        key = f"{org}/{repo}"
        async with state._lock:
            mirror = state.projects.get(key)
            if mirror is not None:
                if ok:
                    mirror.status = MirrorStatus.OK
                    mirror.last_success = datetime.now(timezone.utc)
                    mirror.error_message = ""
                else:
                    mirror.status = MirrorStatus.ERROR
                    mirror.error_message = "Mirror sync trigger failed"
    finally:
        await ge.close()


async def background_worker() -> None:
    """Run periodic full syncs forever."""
    settings = get_settings()
    logger.info(
        "Background worker started – interval=%ds", settings.poll_interval_seconds
    )
    while True:
        await run_full_sync()
        await asyncio.sleep(settings.poll_interval_seconds)
