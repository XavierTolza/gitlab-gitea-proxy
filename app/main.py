"""FastAPI application — web dashboard + REST API."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.services.sync_engine import (
    MirrorStatus,
    ServiceHealth,
    background_worker,
    get_state,
    run_full_sync,
    sync_single_project,
)

logger = logging.getLogger(__name__)

templates = Jinja2Templates(
    directory=os.path.join(os.path.dirname(__file__), "templates")
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Start background sync worker
    task = asyncio.create_task(background_worker())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="GitLab→Gitea MirrorSync", version="1.0.0", lifespan=lifespan)

# Static files (CSS, JS)
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------


@app.get("/api/status")
async def api_status():
    """Return full system state as JSON."""
    state = get_state()
    projects = []
    async with state._lock:
        for key, m in state.projects.items():
            projects.append(
                {
                    "key": key,
                    "gitlab_id": m.gl_id,
                    "gitlab_name": m.gl_name,
                    "gitlab_path": m.gl_path,
                    "gitlab_http_url": m.gl_http_url,
                    "gitea_org": m.gitea_org,
                    "gitea_repo": m.gitea_repo,
                    "gitea_url": m.gitea_url,
                    "status": m.status.value,
                    "last_success": (
                        m.last_success.isoformat() if m.last_success else None
                    ),
                    "error": m.error_message,
                    "error_detail": m.error_detail,
                }
            )
        return {
            "gitlab_health": state.gitlab_health.value,
            "gitea_health": state.gitea_health.value,
            "last_full_scan": (
                state.last_full_scan.isoformat() if state.last_full_scan else None
            ),
            "last_scan_error": state.last_scan_error,
            "projects": projects,
        }


@app.post("/api/sync/all")
async def api_sync_all():
    """Trigger a full discovery + mirror cycle in the background."""
    asyncio.create_task(run_full_sync())
    return {"message": "Full sync started"}


@app.post("/api/sync/{org}/{repo:path}")
async def api_sync_single(org: str, repo: str):
    """Trigger a mirror sync for a specific repo."""
    asyncio.create_task(sync_single_project(org, repo))
    return {"message": f"Sync triggered for {org}/{repo}"}


@app.get("/api/error/{org}/{repo:path}")
async def api_error_detail(org: str, repo: str):
    """Return the detailed error for a specific mirrored project."""
    from app.services.errors import format_error_for_display

    state = get_state()
    key = f"{org}/{repo}"
    async with state._lock:
        mirror = state.projects.get(key)
        if mirror is None:
            return {"error": "Project not found"}
        return {
            "key": key,
            "status": mirror.status.value,
            "error_message": mirror.error_message,
            "error_detail": mirror.error_detail,
            "error_formatted": format_error_for_display(mirror.error_detail),
        }


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Dashboard (SPA-like with Alpine.js polling)
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "gitlab_url": settings.gitlab_url,
            "gitea_url": settings.gitea_url,
            "poll_interval": settings.poll_interval_seconds,
        },
    )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main():
    import uvicorn

    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.web_port, reload=False)


if __name__ == "__main__":
    main()