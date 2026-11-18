# Frontend Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the React UI to the mockup (light/dark) and add soft-delete job dismiss APIs so “Fermer” / “Fermer les terminées” persist.

**Architecture:** Keep Vite/React/shadcn/TanStack Query. Map mockup tokens into CSS variables + `.dark`. Add `jobs.dismissed_at`, application use-cases, and two new job endpoints; regenerate the OpenAPI client; wire dismiss + theme toggle into the existing panels with a two-column layout.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, pytest, React 19, Tailwind v4, shadcn, TanStack Query/Form, hey-api openapi-ts.

**Spec:** `docs/superpowers/specs/2026-11-18-frontend-redesign-design.md`

## Global Constraints

- Soft-delete only (`dismissed_at`); never hard-delete jobs
- `POST /jobs/dismiss-completed` archives **completed** only; failed stay until per-job dismiss
- Active jobs (`pending`/`running`) cannot be dismissed → 409
- `GET /jobs` excludes dismissed jobs
- Theme: `prefers-color-scheme` if no `localStorage` key `anime-downloader.theme`; toggle persists `light`|`dark`
- Do not commit `Anime Downloader.html`; delete it in the final task
- Work on branch `feat/frontend-redesign` from current `main` (use worktree skill at execution)
- French UI copy; English code/docs
- Exhaustive `switch` on unions/enums with `never` default (frontend)
- No inline imports

## File map

| File | Responsibility |
|------|----------------|
| `backend/.../domain/model.py` | `DownloadJob.dismissed_at` |
| `backend/.../domain/errors.py` | `JobCannotBeDismissed` |
| `backend/.../domain/ports.py` | unchanged signatures; save/get/list carry new field |
| `backend/.../application/dismiss_job.py` | `dismiss_job`, `dismiss_completed_jobs` |
| `backend/.../application/get_job.py` | `list_jobs` filters out dismissed |
| `backend/.../infrastructure/db/models.py` | `JobRow.dismissed_at` |
| `backend/alembic/versions/0002_jobs_dismissed_at.py` | migration |
| `backend/.../persistence/job_repository.py` | persist/load `dismissed_at` |
| `backend/.../api/schemas.py` | `DismissCompletedResponse`; optional `dismissed_at` on response |
| `backend/.../api/routes_jobs.py` | dismiss endpoints |
| `backend/.../api/main.py` | map `JobCannotBeDismissed` → 409 |
| `frontend/index.html` | Google fonts link |
| `frontend/src/index.css` | mockup tokens light/dark |
| `frontend/src/lib/theme.ts` | resolve/apply/persist theme |
| `frontend/src/components/ThemeToggle.tsx` | header toggle |
| `frontend/src/components/StatusBadge.tsx` | shared status pills |
| `frontend/src/App.tsx` | shell layout + live indicator |
| `frontend/src/components/UrlDownloadForm.tsx` | restyle |
| `frontend/src/components/JobsPanel.tsx` | restyle + dismiss |
| `frontend/src/components/LibraryPanel.tsx` | restyle + collapse |
| `frontend/openapi.json` + `src/api/client/**` | regenerated |

---

### Task 1: Domain dismiss use-cases (TDD)

**Files:**
- Create: `backend/src/anime_downloader/application/dismiss_job.py`
- Create: `backend/tests/application/test_dismiss_job.py`
- Modify: `backend/src/anime_downloader/domain/model.py`
- Modify: `backend/src/anime_downloader/domain/errors.py`
- Modify: `backend/src/anime_downloader/application/get_job.py`

**Interfaces:**
- Consumes: `JobRepository`, `Clock`, `DownloadJob`, `JobStatus`
- Produces:
  - `dismiss_job(job_id: str, jobs: JobRepository, clock: Clock) -> DownloadJob`
  - `dismiss_completed_jobs(jobs: JobRepository, clock: Clock) -> int`
  - `list_jobs(jobs) -> list[DownloadJob]` returns only jobs with `dismissed_at is None`
  - `JobCannotBeDismissed(DomainError)`
  - `DownloadJob.dismissed_at: str | None = None`

- [ ] **Step 1: Extend `DownloadJob` and add error**

In `domain/model.py`, add field to `DownloadJob`:

```python
dismissed_at: str | None = None
```

In `domain/errors.py`:

```python
class JobCannotBeDismissed(DomainError):
    pass
```

- [ ] **Step 2: Write failing application tests**

Create `backend/tests/application/test_dismiss_job.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from anime_downloader.application.dismiss_job import dismiss_completed_jobs, dismiss_job
from anime_downloader.application.get_job import list_jobs
from anime_downloader.domain.errors import JobCannotBeDismissed, JobNotFound
from anime_downloader.domain.model import DownloadJob, JobStatus
from anime_downloader.infrastructure.db.session import (
    create_engine_for_path,
    make_session_factory,
    run_migrations,
)
from anime_downloader.infrastructure.persistence.job_repository import (
    SqlAlchemyJobRepository,
)


class FixedClock:
    def __init__(self, value: str = "2026-11-18T12:00:00+00:00") -> None:
        self.value = value

    def now_iso(self) -> str:
        return self.value


def _repo(tmp_path: Path) -> SqlAlchemyJobRepository:
    db = tmp_path / "app.db"
    engine = create_engine_for_path(db)
    run_migrations(db)
    return SqlAlchemyJobRepository(make_session_factory(engine))


def _job(**kwargs) -> DownloadJob:
    base = dict(
        id="job-1",
        source_url="https://demo.local/season/show/1",
        adapter_id="demo",
        status=JobStatus.COMPLETED,
        total_episodes=3,
        completed_episodes=3,
    )
    base.update(kwargs)
    return DownloadJob(**base)


def test_dismiss_job_sets_dismissed_at(tmp_path: Path) -> None:
    jobs = _repo(tmp_path)
    jobs.save(_job())
    clock = FixedClock()

    out = dismiss_job("job-1", jobs, clock)

    assert out.dismissed_at == clock.value
    assert list_jobs(jobs) == []
    assert jobs.get("job-1") is not None
    assert jobs.get("job-1").dismissed_at == clock.value


def test_dismiss_job_rejects_active(tmp_path: Path) -> None:
    jobs = _repo(tmp_path)
    jobs.save(_job(status=JobStatus.RUNNING, completed_episodes=1))

    with pytest.raises(JobCannotBeDismissed):
        dismiss_job("job-1", jobs, FixedClock())


def test_dismiss_job_missing_raises(tmp_path: Path) -> None:
    jobs = _repo(tmp_path)
    with pytest.raises(JobNotFound):
        dismiss_job("missing", jobs, FixedClock())


def test_dismiss_completed_skips_failed_and_active(tmp_path: Path) -> None:
    jobs = _repo(tmp_path)
    jobs.save(_job(id="done", status=JobStatus.COMPLETED))
    jobs.save(_job(id="fail", status=JobStatus.FAILED, failed_episodes=1, completed_episodes=2))
    jobs.save(_job(id="run", status=JobStatus.RUNNING, completed_episodes=0))

    count = dismiss_completed_jobs(jobs, FixedClock())

    assert count == 1
    visible = {j.id for j in list_jobs(jobs)}
    assert visible == {"fail", "run"}
```

- [ ] **Step 3: Run tests — expect FAIL**

Run: `cd backend && uv run pytest tests/application/test_dismiss_job.py -v`

Expected: FAIL (import `dismiss_job` missing and/or `dismissed_at` not persisted yet — domain field alone may fail at repo round-trip later; application module missing first).

- [ ] **Step 4: Implement application module + filter list**

Create `backend/src/anime_downloader/application/dismiss_job.py`:

```python
from __future__ import annotations

from anime_downloader.domain.errors import JobCannotBeDismissed, JobNotFound
from anime_downloader.domain.model import DownloadJob, JobStatus
from anime_downloader.domain.ports import Clock, JobRepository

_ACTIVE = {JobStatus.PENDING, JobStatus.RUNNING}


def dismiss_job(job_id: str, jobs: JobRepository, clock: Clock) -> DownloadJob:
    job = jobs.get(job_id)
    if job is None:
        raise JobNotFound(f"Job not found: {job_id}")
    if job.status in _ACTIVE:
        raise JobCannotBeDismissed(
            f"Cannot dismiss job in status {job.status.value}: {job_id}"
        )
    if job.dismissed_at is not None:
        return job
    job.dismissed_at = clock.now_iso()
    return jobs.save(job)


def dismiss_completed_jobs(jobs: JobRepository, clock: Clock) -> int:
    count = 0
    for job in jobs.list_jobs():
        if job.dismissed_at is not None:
            continue
        if job.status != JobStatus.COMPLETED:
            continue
        job.dismissed_at = clock.now_iso()
        jobs.save(job)
        count += 1
    return count
```

Update `get_job.py` `list_jobs`:

```python
def list_jobs(jobs: JobRepository) -> list[DownloadJob]:
    return [job for job in jobs.list_jobs() if job.dismissed_at is None]
```

- [ ] **Step 5: Temporarily skip persistence failures if needed**

If tests fail only because SQLAlchemy ignores unknown `dismissed_at`, proceed to Task 2 before re-running. Prefer implementing Task 2 next in the same session if Step 5 fails on round-trip.

- [ ] **Step 6: Commit** (after Task 2 if persistence required for green)

```bash
git add backend/src/anime_downloader/domain/model.py \
  backend/src/anime_downloader/domain/errors.py \
  backend/src/anime_downloader/application/dismiss_job.py \
  backend/src/anime_downloader/application/get_job.py \
  backend/tests/application/test_dismiss_job.py
git commit -m "$(cat <<'EOF'
Add job dismiss use-cases with soft-delete semantics.

EOF
)"
```

---

### Task 2: Persist `dismissed_at` (migration + repo)

**Files:**
- Modify: `backend/src/anime_downloader/infrastructure/db/models.py`
- Modify: `backend/src/anime_downloader/infrastructure/persistence/job_repository.py`
- Create: `backend/alembic/versions/0002_jobs_dismissed_at.py`
- Modify: `backend/tests/infrastructure/test_sqlalchemy_repos.py`

**Interfaces:**
- Consumes: `DownloadJob.dismissed_at`
- Produces: `JobRow.dismissed_at: Mapped[str | None]`; save/get/list round-trip the field

- [ ] **Step 1: Write failing repo assertion**

Extend `test_job_repository_saves_updates_and_filters_resumable` (or add sibling test):

```python
def test_job_repository_persists_dismissed_at(session_factory) -> None:
    repo = SqlAlchemyJobRepository(session_factory)
    job = DownloadJob(
        id="job-dismissed",
        source_url="https://demo.local/season/show/1",
        adapter_id="demo",
        status=JobStatus.COMPLETED,
        total_episodes=1,
        completed_episodes=1,
        dismissed_at="2026-11-18T12:00:00+00:00",
    )
    repo.save(job)
    loaded = repo.get("job-dismissed")
    assert loaded is not None
    assert loaded.dismissed_at == "2026-11-18T12:00:00+00:00"
```

- [ ] **Step 2: Run — expect FAIL**

Run: `cd backend && uv run pytest tests/infrastructure/test_sqlalchemy_repos.py::test_job_repository_persists_dismissed_at -v`

Expected: FAIL (column missing / attribute missing).

- [ ] **Step 3: Add column on model + migration**

In `JobRow`:

```python
dismissed_at: Mapped[str | None] = mapped_column(String, nullable=True)
```

Create `backend/alembic/versions/0002_jobs_dismissed_at.py`:

```python
"""Add jobs.dismissed_at for soft-delete.

Revision ID: 0002_jobs_dismissed_at
Revises: 0001_initial_schema
Create Date: 2026-11-18 18:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0002_jobs_dismissed_at"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("dismissed_at", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "dismissed_at")
```

- [ ] **Step 4: Update repository mapping**

In `save()` update + insert paths, set `row.dismissed_at = job.dismissed_at`.

In `_to_job`:

```python
dismissed_at=row.dismissed_at,
```

- [ ] **Step 5: Run tests**

Run:

```bash
cd backend && uv run pytest tests/infrastructure/test_sqlalchemy_repos.py::test_job_repository_persists_dismissed_at tests/application/test_dismiss_job.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/src/anime_downloader/infrastructure/db/models.py \
  backend/src/anime_downloader/infrastructure/persistence/job_repository.py \
  backend/alembic/versions/0002_jobs_dismissed_at.py \
  backend/tests/infrastructure/test_sqlalchemy_repos.py \
  backend/src/anime_downloader/domain/model.py \
  backend/src/anime_downloader/domain/errors.py \
  backend/src/anime_downloader/application/dismiss_job.py \
  backend/src/anime_downloader/application/get_job.py \
  backend/tests/application/test_dismiss_job.py
git commit -m "$(cat <<'EOF'
Persist job soft-delete via dismissed_at column.

EOF
)"
```

---

### Task 3: HTTP dismiss endpoints

**Files:**
- Modify: `backend/src/anime_downloader/api/schemas.py`
- Modify: `backend/src/anime_downloader/api/routes_jobs.py`
- Modify: `backend/src/anime_downloader/api/main.py`
- Modify: `backend/src/anime_downloader/api/deps.py` (wire `Clock` if not already exposed)
- Modify: `backend/tests/api/test_jobs_api.py`

**Interfaces:**
- Consumes: `dismiss_job`, `dismiss_completed_jobs`, `SystemClock` / `get_clock`
- Produces:
  - `POST /api/jobs/{id}/dismiss` → `JobResponse` (include `dismissed_at`)
  - `POST /api/jobs/dismiss-completed` → `DismissCompletedResponse(dismissed_count: int)`
  - `JobCannotBeDismissed` → HTTP 409

- [ ] **Step 1: Write failing API tests**

Append to `test_jobs_api.py`:

```python
def test_dismiss_job_and_dismiss_completed(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    with TestClient(app) as client:
        created = client.post(
            "/api/jobs",
            json={"url": "https://demo.local/season/demo-show/1"},
        )
        assert created.status_code == 201
        job_id = created.json()["id"]

        _poll_until(
            lambda: client.get(f"/api/jobs/{job_id}").json()["status"]
            in {"completed", "failed"}
        )

        listed_before = client.get("/api/jobs")
        assert listed_before.status_code == 200
        assert any(j["id"] == job_id for j in listed_before.json())

        dismissed = client.post(f"/api/jobs/{job_id}/dismiss")
        assert dismissed.status_code == 200
        assert dismissed.json()["dismissed_at"] is not None

        listed_after = client.get("/api/jobs")
        assert all(j["id"] != job_id for j in listed_after.json())


def test_dismiss_active_job_conflict(tmp_path: Path) -> None:
    release = threading.Event()

    class GatedDownloader:
        def download(self, media, destination, *, on_progress=None) -> str:
            release.wait(timeout=5.0)
            return FakeMediaDownloader(payload=b"x").download(media, destination)

    app = create_app(tmp_path, downloader=GatedDownloader())
    with TestClient(app) as client:
        created = client.post(
            "/api/jobs",
            json={"url": "https://demo.local/season/demo-show/1"},
        )
        job_id = created.json()["id"]
        _poll_until(
            lambda: client.get(f"/api/jobs/{job_id}").json()["status"] == "running"
        )
        resp = client.post(f"/api/jobs/{job_id}/dismiss")
        assert resp.status_code == 409
        release.set()


def test_dismiss_completed_endpoint_counts(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    with TestClient(app) as client:
        created = client.post(
            "/api/jobs",
            json={"url": "https://demo.local/season/demo-show/1"},
        )
        job_id = created.json()["id"]
        _poll_until(
            lambda: client.get(f"/api/jobs/{job_id}").json()["status"] == "completed"
        )
        resp = client.post("/api/jobs/dismiss-completed")
        assert resp.status_code == 200
        assert resp.json() == {"dismissed_count": 1}
        assert client.get("/api/jobs").json() == []
```

- [ ] **Step 2: Run — expect FAIL**

Run: `cd backend && uv run pytest tests/api/test_jobs_api.py::test_dismiss_job_and_dismiss_completed tests/api/test_jobs_api.py::test_dismiss_active_job_conflict tests/api/test_jobs_api.py::test_dismiss_completed_endpoint_counts -v`

Expected: FAIL (404 on unknown routes).

- [ ] **Step 3: Schemas + error mapping + routes**

`schemas.py`:

```python
class DismissCompletedResponse(BaseModel):
    dismissed_count: int
```

Add to `JobResponse`:

```python
dismissed_at: str | None = None
```

`main.py` `_status_for_domain_error`:

```python
from anime_downloader.domain.errors import JobCannotBeDismissed
# ...
if isinstance(exc, (NoFailedEpisodes, JobCannotBeDismissed)):
    return status.HTTP_409_CONFLICT
```

In `deps.py`, expose clock if missing:

```python
def get_clock(request: Request) -> Clock:
    return request.app.state.container.clock
```

(Ensure `AppContainer` already has `clock: SystemClock` — add if absent.)

In `routes_jobs.py` (register **before** `/{id}` if needed; these paths are distinct):

```python
from anime_downloader.application.dismiss_job import (
    dismiss_completed_jobs,
    dismiss_job,
)
from anime_downloader.api.schemas import DismissCompletedResponse
from anime_downloader.domain.ports import Clock
from anime_downloader.api.deps import get_clock

@router.post(
    "/dismiss-completed",
    response_model=DismissCompletedResponse,
    operation_id="dismissCompletedJobs",
)
def dismiss_completed_endpoint(
    jobs: Annotated[JobRepository, Depends(get_job_repository)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> DismissCompletedResponse:
    return DismissCompletedResponse(
        dismissed_count=dismiss_completed_jobs(jobs, clock)
    )


@router.post(
    "/{id}/dismiss",
    response_model=JobResponse,
    operation_id="dismissJob",
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def dismiss_job_endpoint(
    id: str,
    jobs: Annotated[JobRepository, Depends(get_job_repository)],
    clock: Annotated[Clock, Depends(get_clock)],
    worker: Annotated[DownloadWorker, Depends(get_worker)],
) -> JobResponse:
    job = dismiss_job(id, jobs, clock)
    return _job_response(job, worker)
```

- [ ] **Step 4: Run API tests — PASS**

Run: `cd backend && uv run pytest tests/api/test_jobs_api.py -v`

Expected: PASS (existing + new).

- [ ] **Step 5: Commit**

```bash
git add backend/src/anime_downloader/api/schemas.py \
  backend/src/anime_downloader/api/routes_jobs.py \
  backend/src/anime_downloader/api/main.py \
  backend/src/anime_downloader/api/deps.py \
  backend/tests/api/test_jobs_api.py
git commit -m "$(cat <<'EOF'
Expose dismiss job HTTP endpoints with soft-delete.

EOF
)"
```

---

### Task 4: Regenerate OpenAPI client

**Files:**
- Modify: `frontend/openapi.json`
- Modify: `frontend/src/api/client/**` (generated)

**Interfaces:**
- Produces: `dismissJobMutation`, `dismissCompletedJobsMutation` (hey-api names)

- [ ] **Step 1: Export + generate**

From repo root:

```bash
task openapi
```

(If Task target differs, use the existing `openapi` / export task from `Taskfile.yml` that writes `frontend/openapi.json` then `npm run openapi-ts`.)

- [ ] **Step 2: Verify generated symbols**

```bash
rg -n "dismissJob|dismissCompletedJobs" frontend/src/api/client -g '*.ts' | head
```

Expected: mutation helpers present.

- [ ] **Step 3: Commit**

```bash
git add frontend/openapi.json frontend/src/api/client
git commit -m "$(cat <<'EOF'
Regenerate OpenAPI client for job dismiss endpoints.

EOF
)"
```

---

### Task 5: Theme tokens + toggle

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/src/index.css`
- Create: `frontend/src/lib/theme.ts`
- Create: `frontend/src/components/ThemeToggle.tsx`
- Modify: `frontend/src/main.tsx` (call `initTheme()` before render)

**Interfaces:**
- Produces:
  - `initTheme(): void`
  - `getTheme(): 'light' | 'dark'`
  - `setTheme(theme: 'light' | 'dark'): void`
  - `toggleTheme(): 'light' | 'dark'`
  - storage key `anime-downloader.theme`

- [ ] **Step 1: Fonts in `index.html`**

```html
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link
  href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=JetBrains+Mono:wght@400;500&family=Manrope:wght@400;700&display=swap"
  rel="stylesheet"
/>
```

Set `<html lang="fr">`.

- [ ] **Step 2: Replace `:root` / `.dark` tokens in `index.css`**

Map mockup tokens onto shadcn variables (keep `@theme inline` wiring). Core values:

```css
:root {
  --radius: 0.4375rem; /* ~7px */
  --background: #f2f5f8;
  --foreground: #030616;
  --card: #ffffff;
  --card-foreground: #030616;
  --primary: #030616;
  --primary-foreground: #ffffff;
  --secondary: #f2f5f8;
  --secondary-foreground: #030616;
  --muted: #f2f5f8;
  --muted-foreground: #46556c;
  --accent: #deebf8;
  --accent-foreground: #224873;
  --destructive: #a1261b;
  --border: #e3e8f0;
  --input: #cdd5df;
  --ring: #336fad;
  --ad-soft: #46556c;
  --ad-muted: #6b7280;
  --ad-live: #336fad;
  --ad-inset: #f2f5f8;
  --ad-tile: #192840;
  --ad-ok-bg: #eaf1ed;
  --ad-ok-fg: #44534a;
  --ad-err-bg: #fdecea;
  --ad-err-fg: #a1261b;
  --ad-track: #e3e8f0;
  --font-sans: Inter, system-ui, -apple-system, "Segoe UI", sans-serif;
  --font-display: Manrope, Inter, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, monospace;
}

.dark {
  --background: #030616;
  --foreground: #ffffff;
  --card: #0c1024;
  --card-foreground: #ffffff;
  --primary: #ffffff;
  --primary-foreground: #030616;
  --secondary: #151b33;
  --secondary-foreground: #ffffff;
  --muted: #151b33;
  --muted-foreground: #cdd5df;
  --accent: rgba(118, 169, 221, 0.18);
  --accent-foreground: #a8c9eb;
  --destructive: #fda29b;
  --border: rgba(255, 255, 255, 0.10);
  --input: rgba(255, 255, 255, 0.20);
  --ring: #76a9dd;
  --ad-soft: #cdd5df;
  --ad-muted: #99a9bd;
  --ad-live: #76a9dd;
  --ad-inset: #151b33;
  --ad-tile: #224873;
  --ad-ok-bg: rgba(124, 164, 141, 0.18);
  --ad-ok-fg: #aecebb;
  --ad-err-bg: rgba(240, 68, 56, 0.14);
  --ad-err-fg: #fda29b;
  --ad-track: rgba(255, 255, 255, 0.10);
}
```

Add base font utilities on `body` using `--font-sans`. Add `@keyframes adPulse` + `.ad-pulse`.

- [ ] **Step 3: Implement `theme.ts`**

```typescript
export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'anime-downloader.theme';

function systemTheme(): Theme {
  if (typeof window === 'undefined') return 'light';
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export function getStoredTheme(): Theme | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    if (value === 'light' || value === 'dark') return value;
  } catch {
    /* ignore */
  }
  return null;
}

export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  root.classList.toggle('dark', theme === 'dark');
  root.style.colorScheme = theme;
}

export function initTheme(): Theme {
  const theme = getStoredTheme() ?? systemTheme();
  applyTheme(theme);
  return theme;
}

export function setTheme(theme: Theme): void {
  applyTheme(theme);
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    /* ignore */
  }
}

export function toggleTheme(): Theme {
  const next: Theme = document.documentElement.classList.contains('dark')
    ? 'light'
    : 'dark';
  setTheme(next);
  return next;
}

export function getTheme(): Theme {
  return document.documentElement.classList.contains('dark') ? 'dark' : 'light';
}
```

- [ ] **Step 4: `ThemeToggle.tsx` + call `initTheme()` in `main.tsx`**

Button: 36×36 pill, sun/moon via `lucide-react` (`Sun`, `Moon`), `aria-label` from current theme (“Passer en mode sombre” / “Passer en mode clair”).

- [ ] **Step 5: Verify build**

```bash
cd frontend && npm run build
```

Expected: success.

- [ ] **Step 6: Commit**

```bash
git add frontend/index.html frontend/src/index.css frontend/src/lib/theme.ts \
  frontend/src/components/ThemeToggle.tsx frontend/src/main.tsx
git commit -m "$(cat <<'EOF'
Add mockup theme tokens and light/dark toggle.

EOF
)"
```

---

### Task 6: App shell layout

**Files:**
- Modify: `frontend/src/App.tsx`
- Optional create: `frontend/src/components/AppHeader.tsx`

**Interfaces:**
- Consumes: `listJobsOptions` for live indicator; `ThemeToggle`
- Produces: header + max-width 1160 layout; jobs|library two-column grid

- [ ] **Step 1: Rewrite `App.tsx` structure**

```tsx
export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <div className="min-h-screen bg-background text-foreground font-sans">
        <AppHeader />
        <main className="mx-auto flex max-w-[1160px] flex-col gap-8 px-6 py-10 pb-16">
          <UrlDownloadForm />
          <div className="flex flex-wrap items-start gap-8">
            <div className="min-w-0 flex-1 basis-[360px]">
              <JobsPanel />
            </div>
            <div className="min-w-0 flex-[999_1_560px]">
              <LibraryPanel />
            </div>
          </div>
        </main>
      </div>
    </QueryClientProvider>
  );
}
```

`AppHeader`: white/`bg-card` bar, bottom border, logo 36×36 `bg-primary` with download icon, title Manrope bold, live pulse when any job `pending`|`running`, `ThemeToggle`.

- [ ] **Step 2: `npm run build` — PASS**

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/AppHeader.tsx
git commit -m "$(cat <<'EOF'
Restructure app shell to match mockup layout.

EOF
)"
```

---

### Task 7: Restyle `UrlDownloadForm`

**Files:**
- Modify: `frontend/src/components/UrlDownloadForm.tsx`
- Modify: `frontend/src/components/ui/button.tsx` (optional pill size if needed)

**Interfaces:**
- Consumes: existing preview/create mutations (unchanged API)
- Produces: mockup card UI (eyebrow, H1, mono input, pill CTA, preview strip)

- [ ] **Step 1: Restyle keeping form logic**

Keep `urlSchema`, preview-on-blur, create mutation. Visual requirements:

- Card: `rounded-[7px] border border-border bg-card p-8`
- Eyebrow: `text-xs font-semibold tracking-[0.12em] text-[#2c5c8e] dark:text-[#76a9dd]`
- Title: `font-[family-name:var(--font-display)] text-[32px] font-normal`
- Input: `h-12 font-mono`, button: `h-12 rounded-full`
- Success strip: inset bg `--ad-inset` / ok icon
- Error strip: `--ad-err-bg` / `--ad-err-fg`

- [ ] **Step 2: Build**

```bash
cd frontend && npm run build
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/UrlDownloadForm.tsx frontend/src/components/ui/button.tsx
git commit -m "$(cat <<'EOF'
Restyle season download form to match mockup.

EOF
)"
```

---

### Task 8: Restyle `JobsPanel` + dismiss actions

**Files:**
- Modify: `frontend/src/components/JobsPanel.tsx`
- Create: `frontend/src/components/StatusBadge.tsx`

**Interfaces:**
- Consumes: `dismissJobMutation`, `dismissCompletedJobsMutation`, `retryFailedEpisodesMutation`, `listJobsOptions`
- Produces: dismiss X, “Fermer les terminées”, badges, progress bars, empty state

- [ ] **Step 1: Implement `StatusBadge`**

Props: `kind: 'done' | 'running' | 'waiting' | 'failed' | 'skipped'`, optional `label`. Styles from mockup light/dark (use CSS vars / Tailwind tokens added in Task 5). Running uses `ad-pulse` on the dot.

Map:

- job `completed` → done / “Terminé”
- job `running` → running / “En cours”
- job `pending` → waiting / “En attente”
- job `failed` → failed / “Échec” or “Échec partiel” when partial

- [ ] **Step 2: Wire dismiss mutations in `JobsPanel`**

```tsx
const dismissMutation = useMutation({
  ...dismissJobMutation(),
  onSuccess: async () => {
    await queryClient.invalidateQueries({ queryKey: listJobsQueryKey() });
  },
});

const dismissCompletedMutation = useMutation({
  ...dismissCompletedJobsMutation(),
  onSuccess: async () => {
    await queryClient.invalidateQueries({ queryKey: listJobsQueryKey() });
  },
});
```

Show “Fermer les terminées” when `jobs.some(j => j.status === 'completed')`.

Dismiss button only if `status === 'completed' || status === 'failed'`.

Error messages FR:

- dismiss 409 → `Impossible de fermer une tâche en cours.`
- dismiss 404 → `Tâche introuvable.`

- [ ] **Step 3: Visual job cards**

Match mockup: title · season, mono URL, badge, season progress `completed/total`, optional episode progress from `current_episode_number` / `episode_progress_percent`, error strip + retry, adapter line. Empty dashed card when `jobs.length === 0`.

- [ ] **Step 4: Build**

```bash
cd frontend && npm run build
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/JobsPanel.tsx frontend/src/components/StatusBadge.tsx
git commit -m "$(cat <<'EOF'
Restyle jobs panel and wire soft-delete dismiss actions.

EOF
)"
```

---

### Task 9: Restyle `LibraryPanel` + collapse

**Files:**
- Modify: `frontend/src/components/LibraryPanel.tsx`

**Interfaces:**
- Consumes: `listLibraryOptions` (unchanged)
- Produces: collapsible series, initials tile, episode rows + badges, summary counts

- [ ] **Step 1: Add local expand state**

```tsx
const [openIds, setOpenIds] = useState<Record<string, boolean>>({});
```

Default: first series open when data loads (set once when `seriesList` goes from empty → non-empty).

- [ ] **Step 2: Restyle**

- Header with counts: `N séries · M épisodes sur disque` (`completed` count)
- Series button row: 44×44 tile with initials from title, meta (seasons/episodes), badge if any failed/downloading
- Expanded seasons: episode grid columns `64px | 1fr | auto`
- Use `StatusBadge` for episode statuses (`downloading`→running, `pending`→waiting, `completed`→done, etc.)
- Optional: collapse consecutive completed episodes beyond 3 into an “Afficher” group row (mockup behavior); if timeboxed, ship expand-all rows first and add grouping as follow-up only if still within task

- [ ] **Step 3: Build**

```bash
cd frontend && npm run build
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/LibraryPanel.tsx
git commit -m "$(cat <<'EOF'
Restyle library panel with collapsible series.

EOF
)"
```

---

### Task 10: Cleanup mockup + verify

**Files:**
- Delete: `Anime Downloader.html` (repo root)

- [ ] **Step 1: Delete mockup**

```bash
rm -f "Anime Downloader.html"
```

- [ ] **Step 2: Full verification**

```bash
cd backend && uv run pytest -v
cd ../frontend && npm run build && npm run lint
```

Expected: all green.

- [ ] **Step 3: Manual smoke** (if Docker/dev available)

```bash
task docker:up   # or task frontend + task backend
```

Check: light/dark toggle, preview form, dismiss, clear completed, library collapse.

- [ ] **Step 4: Commit**

```bash
git add -A
git status
git commit -m "$(cat <<'EOF'
Remove design mockup HTML after frontend redesign.

EOF
)"
```

---

## Self-review (plan vs spec)

| Spec requirement | Task |
|------------------|------|
| Light/dark tokens + toggle (system then persist) | 5 |
| Header + two-column layout | 6 |
| Form restyle | 7 |
| Jobs badges/progress/empty + dismiss UI | 8 |
| Soft-delete model + endpoints | 1–3 |
| OpenAPI client | 4 |
| Library collapse | 9 |
| Delete HTML mockup | 10 |
| Dedicated branch | execution via worktree / branch `feat/frontend-redesign` |
| Accent picker | out of scope |
| Hard-delete | out of scope |

No TBD/TODO placeholders remain. Types align: `dismissed_at: str | None`, `DismissCompletedResponse.dismissed_count: int`, theme `'light' | 'dark'`.
