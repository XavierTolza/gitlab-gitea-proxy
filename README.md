# GitLab → Gitea MirrorSync

Service autonome de découverte et réplication automatique de projets GitLab vers Gitea, avec interface web de monitoring.

## Phase 0 — API Research Summary

### GitLab REST API v4

| Endpoint | Usage |
|---|---|
| `GET /api/v4/version` | Health check |
| `GET /api/v4/groups/:id` | Resolve group path → numeric ID |
| `GET /api/v4/groups/:id/projects?include_subgroups=true&archived=false&with_shared=false` | List all projects recursively |
| `GET /api/v4/groups/:id/subgroups` | List direct subgroups |

**Auth**: Header `PRIVATE-TOKEN: <glpat-...>`  
**Pagination**: `?per_page=100&page=N`, stop when response < 100 items.

### Gitea REST API v1

| Endpoint | Usage |
|---|---|
| `GET /api/v1/version` | Health check |
| `POST /api/v1/orgs` | Create organisation `{username, full_name}` |
| `GET /api/v1/orgs/:org` | Check if org exists |
| `POST /api/v1/repos/migrate` | Create mirrored repo |
| `GET /api/v1/repos/:owner/:repo` | Check if repo exists |
| `POST /api/v1/repos/:owner/:repo/mirror-sync` | Trigger manual mirror sync |

**Auth**: Header `Authorization: token <gitea_token>`  
**Migrate payload**:
```json
{
  "clone_addr": "https://gitlab.com/group/project.git",
  "auth_token": "glpat-...",
  "mirror": true,
  "repo_name": "project",
  "repo_owner": "org-name",
  "service": "gitlab"
}
```

### Path Mapping Logic

GitLab `group/subgroup/project` → Gitea `root-org-subgroup` org + `project` repo.  
The deepest folder becomes the organisation, the project name stays as-is.

## Quick Start

### 1. Clone & Configure

```bash
cp .env.example .env
# Edit .env with your GitLab and Gitea tokens
```

### 2. Run with Docker Compose

```bash
docker compose up -d
```

This starts:
- **Gitea** on `http://localhost:3000` (local instance for mirrors)
- **MirrorSync** on `http://localhost:8000` (dashboard + API)

### 3. Initial Gitea Setup

On first launch, create an admin token:

```bash
docker compose exec gitea gitea admin user create \
  --username admin --password admin1234 --email admin@local.dev --admin
# Then generate a token via the Gitea UI at http://localhost:3000/user/settings/applications
# Paste it as GITEA_TOKEN in .env and restart
```

### 4. Open the Dashboard

Navigate to **http://localhost:8000** to see sync status and trigger operations.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `GITLAB_URL` | *(required)* | GitLab instance base URL |
| `GITLAB_TOKEN` | *(required)* | GitLab Personal Access Token (`read_api` scope) |
| `GITLAB_TARGET_GROUP` | *(required)* | Group ID or URL-encoded path |
| `GITEA_URL` | *(required)* | Gitea instance base URL |
| `GITEA_TOKEN` | *(required)* | Gitea Personal Access Token (`write:repository`, `write:organization`) |
| `GITEA_TARGET_ORG` | `gitlab-backup` | Root Gitea organisation for mirrors |
| `POLL_INTERVAL_SECONDS` | `600` | Scan frequency in seconds |
| `WEB_PORT` | `8000` | Dashboard port |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Web dashboard (HTML) |
| `GET` | `/api/status` | Full system state as JSON |
| `POST` | `/api/sync/all` | Trigger full discovery + mirror cycle |
| `POST` | `/api/sync/{org}/{repo}` | Trigger mirror sync for one project |
| `GET` | `/healthz` | Health check (returns `{"status": "ok"}`) |

## Running Tests

### Local Tests (Gitea only — no GitLab credentials needed)

```bash
pip install -r requirements.txt
pip install pytest pytest-asyncio pytest-timeout testcontainers httpx
pytest tests/test_gitea_client.py -v --timeout=120
```

### Integration Tests (require GitLab access)

```bash
export TEST_GITLAB_URL=https://gitlab.com
export TEST_GITLAB_TOKEN=glpat-your-test-token
export TEST_GITLAB_TARGET_GROUP=your-test-group

pytest tests/ -v --timeout=180
```

## Project Structure

```
.
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── README.md
├── .github/workflows/ci.yml
├── app/
│   ├── main.py              # FastAPI application entrypoint
│   ├── config.py            # Pydantic settings
│   ├── services/
│   │   ├── gitlab_client.py # GitLab API v4 wrapper (httpx)
│   │   ├── gitea_client.py  # Gitea API v1 wrapper (httpx)
│   │   └── sync_engine.py   # Orchestration + in-memory state
│   ├── templates/
│   │   └── dashboard.html   # Alpine.js dashboard
│   └── static/
└── tests/
    ├── conftest.py           # Docker fixtures (Gitea testcontainer)
    ├── test_gitlab_client.py
    ├── test_gitea_client.py
    └── test_integration_sync.py
```

## Architecture

```
┌─────────────┐       ┌──────────────────┐       ┌─────────────┐
│   GitLab    │◄──────│   MirrorSync     │──────►│    Gitea    │
│  (source)   │  REST │  (this service)  │  REST │  (target)   │
└─────────────┘       │  ┌────────────┐  │       └─────────────┘
                      │  │ Sync Engine │  │
                      │  │ (periodic)  │  │
                      │  └────────────┘  │
                      │  ┌────────────┐  │
                      │  │  FastAPI    │──│──► Web Dashboard
                      │  │  Dashboard  │  │    (port 8000)
                      │  └────────────┘  │
                      └──────────────────┘
```

## Token Scopes Required

### GitLab
- `read_api` — to list groups and projects

### Gitea
- `write:repository` — to create mirrored repos
- `write:organization` — to create orgs representing GitLab subgroups
- `read:organization` — to check org existence

---

*This project was generated by an AI agent (OpenHands).*