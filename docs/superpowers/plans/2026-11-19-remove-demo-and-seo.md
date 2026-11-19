# Remove Demo Vestiges & Repo Discoverability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scrub remaining demo-adapter vestiges from code/tests/product docs and fill English GitHub + package metadata for discoverability.

**Architecture:** No new runtime features. Rename/delete demo-flavored test fixtures; remove legacy `/season/...` URL parsing from the jobs UI; strengthen README opening + `description` fields; set GitHub About via `gh`.

**Tech Stack:** pytest, FastAPI TestClient, React/TypeScript (Vite), `gh` CLI, GitHub repository metadata

## Global Constraints

- Spec: `docs/superpowers/specs/2026-11-19-remove-demo-and-seo-design.md`
- Branch: `chore/remove-demo-and-seo` (already exists; design commit is on it)
- English-only public metadata (GitHub description, topics, README polish, package descriptions)
- Do **not** edit historical files under `docs/superpowers/specs/` or `docs/superpowers/plans/` for demo wording (except this plan / its design sibling)
- Do **not** reintroduce a production demo adapter
- Acceptance: zero matches in `backend/src`, `backend/tests`, `frontend/src`, root/product READMEs for `DemoAdapter`, `demo_adapter`, `demo.local`, `adapter_id="demo"`, `demo-show`, `solo-demo`

---

## File structure

| File | Responsibility |
|------|----------------|
| `backend/tests/infrastructure/test_sqlalchemy_repos.py` | Replace `adapter_id="demo"` and path `demo-show` |
| `backend/tests/api/test_jobs_api.py` | Rename `demo-show` / `solo-demo` fixtures |
| `backend/tests/infrastructure/test_worker.py` | Rename `demo-show` fixtures |
| `backend/tests/infrastructure/test_library_migrator.py` | Unknown-host case: drop `demo.local` / `demo-show` |
| `frontend/src/components/JobsPanel.tsx` | Anime-Sama-only season label parsing |
| `README.md` | Stronger English opening for search |
| `backend/pyproject.toml` | `[project].description` |
| `frontend/package.json` | `"description"` |
| GitHub About (remote) | Description + topics via `gh repo edit` |

---

### Task 1: Neutralize backend test fixtures

**Files:**
- Modify: `backend/tests/infrastructure/test_sqlalchemy_repos.py`
- Modify: `backend/tests/api/test_jobs_api.py`
- Modify: `backend/tests/infrastructure/test_worker.py`
- Modify: `backend/tests/infrastructure/test_library_migrator.py`
- Test: same files (rename-only; behavior unchanged)

**Interfaces:**
- Consumes: `FakeSeasonAdapter.adapter_id == "fake"`; fake season URLs `https://fake.local/season/{title}/{n}`
- Produces: tests with no `demo-show`, `solo-demo`, `demo.local`, or `adapter_id="demo"`

- [ ] **Step 1: Replace `adapter_id="demo"` and `demo-show` path in sqlalchemy repo tests**

In `backend/tests/infrastructure/test_sqlalchemy_repos.py`, replace every `adapter_id="demo"` with `adapter_id="fake"`.

Replace the destination path that uses `demo-show`:

```python
dest = tmp_path / "library" / "fake-show" / "1" / "E01.mp4"
```

(Use whatever local variable currently builds under `demo-show`; keep the rest of that test identical.)

- [ ] **Step 2: Rename API test series titles**

In `backend/tests/api/test_jobs_api.py`, apply these renames consistently (URLs, JSON expectations, filesystem paths):

| Old | New |
|-----|-----|
| `demo-show` | `fake-show` |
| `solo-demo` | `solo-show` |

Example expectations after rename:

```python
json={"url": "https://fake.local/season/fake-show/1"}
# ...
"series_title": "fake-show",
# ...
assert lib_data[0]["title"] == "fake-show"
```

```python
json={"url": "https://fake.local/season/solo-show/1"}
# ...
tmp_path / "library" / "solo-show (2020)" / "Season 01" / "solo-show S01E01.mp4"
```

- [ ] **Step 3: Rename worker test series titles**

In `backend/tests/infrastructure/test_worker.py`, rename all `demo-show` occurrences (URLs, titles, path segments) to `fake-show`. Leave other show names (`retry-show`, `hells-paradise`, etc.) unchanged.

- [ ] **Step 4: Rewrite unknown-host migrator fixture (no `demo.local`)**

In `backend/tests/infrastructure/test_library_migrator.py`, update `test_skips_unknown_host_and_leaves_file` so the unknown host is not demo-branded:

```python
def test_skips_unknown_host_and_leaves_file(tmp_path: Path, session_factory, caplog) -> None:
    library_root = tmp_path / "library"
    repo = _repo(session_factory)
    old_path = library_root / "orphan-show" / "1" / "S01E01 - orphan-show.mp4"
    source_url = "https://unknown.local/watch/1"
    _completed_episode(
        repo,
        series_id="s-orphan",
        title="orphan-show",
        season_id="sea-orphan",
        episode_id="ep-orphan",
        number=1,
        source_url=source_url,
        file_path=old_path,
        payload=b"orphan-bytes",
    )

    with caplog.at_level("WARNING"):
        report = migrate_library(
            library=repo,
            registry=AdapterRegistry([_MetaAdapter()]),
            library_root=library_root,
        )

    assert old_path.read_bytes() == b"orphan-bytes"
    assert repo.list_series() == [Series(id="s-orphan", title="orphan-show", release_year=None)]
    assert report.renamed_files == 0
    assert report.merged_series == 0
    assert any("unknown.local" in error for error in report.errors)
    assert any("unknown.local" in record.message for record in caplog.records)
```

Do **not** use `fake.local` here — that host is registered by `FakeSeasonAdapter` and would change the test meaning.

- [ ] **Step 5: Run targeted backend tests**

Run:

```bash
cd backend && uv run pytest \
  tests/infrastructure/test_sqlalchemy_repos.py \
  tests/api/test_jobs_api.py \
  tests/infrastructure/test_worker.py \
  tests/infrastructure/test_library_migrator.py::test_skips_unknown_host_and_leaves_file \
  -v
```

Expected: all PASS.

- [ ] **Step 6: Sweep tests for forbidden demo tokens**

Run:

```bash
cd backend && rg -n 'DemoAdapter|demo_adapter|demo\.local|adapter_id=["'\'']demo["'\'']|demo-show|solo-demo' tests || true
```

Expected: no matches.

- [ ] **Step 7: Commit**

```bash
git add \
  backend/tests/infrastructure/test_sqlalchemy_repos.py \
  backend/tests/api/test_jobs_api.py \
  backend/tests/infrastructure/test_worker.py \
  backend/tests/infrastructure/test_library_migrator.py
git commit -m "$(cat <<'EOF'
Neutralize demo-flavored backend test fixtures.

EOF
)"
```

---

### Task 2: Remove legacy demo URL parsing from JobsPanel

**Files:**
- Modify: `frontend/src/components/JobsPanel.tsx`
- Test: no frontend unit runner; verify with `npm run build` in `frontend/`

**Interfaces:**
- Consumes: Anime-Sama pathname `/catalogue/{slug}/saison{N}`
- Produces: `parseJobSeasonLabel(sourceUrl)` → `{ title, season }` with catalogue match or raw-URL fallback only

- [ ] **Step 1: Rewrite `parseJobSeasonLabel` without `/season/...` branch**

Replace the function in `frontend/src/components/JobsPanel.tsx` with:

```tsx
function parseJobSeasonLabel(sourceUrl: string): { title: string; season: string | null } {
  try {
    const { pathname } = new URL(sourceUrl);
    const catalogueMatch = pathname.match(/\/catalogue\/([^/]+)\/saison(\d+)/i);
    if (catalogueMatch) {
      return { title: humanizeSlug(catalogueMatch[1]), season: catalogueMatch[2] };
    }
  } catch {
    // fall through
  }
  return { title: sourceUrl, season: null };
}
```

Ensure no leftover `demoMatch` identifier remains in the file.

- [ ] **Step 2: Typecheck / build frontend**

Run:

```bash
cd frontend && npm run build
```

Expected: build succeeds (tsc + vite).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/JobsPanel.tsx
git commit -m "$(cat <<'EOF'
Drop legacy demo season URL parsing from job labels.

EOF
)"
```

---

### Task 3: In-repo discoverability metadata

**Files:**
- Modify: `README.md`
- Modify: `backend/pyproject.toml`
- Modify: `frontend/package.json`

**Interfaces:**
- Consumes: approved GitHub one-liner from the design spec
- Produces: searchable README intro + package `description` fields in English

- [ ] **Step 1: Strengthen root README opening**

Replace the first paragraph block under `# anime-downloader` with:

```markdown
# anime-downloader

Self-hosted anime season downloader: paste a supported season URL, preview episodes, and save files into a local Jellyfin-friendly TV library (`Title (Year)/Season NN/...`).

Works with Docker or a native backend + Vite UI. The UI is in French; code and docs are in English. Current source adapter: Anime-Sama (`anime-sama.to`).
```

Keep the rest of the README (adapters table, quick start, how to use, local dev, stack, docs) unchanged unless a demo mention appears (there should be none).

- [ ] **Step 2: Add `description` to `backend/pyproject.toml`**

Under `[project]`, immediately after `name` / `version` (order may match existing style), ensure:

```toml
[project]
name = "anime-downloader"
version = "0.1.0"
description = "Download anime seasons from supported URLs into a local Jellyfin-friendly library (Docker or native)."
requires-python = ">=3.15"
```

Keep existing dependencies and tool sections unchanged.

- [ ] **Step 3: Add `description` to `frontend/package.json`**

```json
{
  "name": "anime-downloader-frontend",
  "private": true,
  "version": "0.0.0",
  "description": "Web UI for the anime-downloader local season download app.",
  "type": "module",
```

Keep scripts/dependencies unchanged.

- [ ] **Step 4: Confirm product READMEs have no demo adapter**

Run:

```bash
rg -n 'DemoAdapter|demo\.local|demo adapter|demo-show' README.md backend/README.md frontend/README.md || true
```

Expected: no matches.

- [ ] **Step 5: Commit**

```bash
git add README.md backend/pyproject.toml frontend/package.json
git commit -m "$(cat <<'EOF'
Add English package descriptions and tighten README discoverability.

EOF
)"
```

---

### Task 4: GitHub About, full test sweep, acceptance

**Files:**
- Remote only: GitHub repository About (description + topics)
- Verify: all prior file changes already committed

**Interfaces:**
- Consumes: exact description/topics from design spec
- Produces: public GitHub metadata + green full backend suite

- [ ] **Step 1: Set GitHub description and topics**

Run (requires network + `gh` auth):

```bash
gh repo edit \
  --description "Download anime seasons from supported URLs into a local Jellyfin-friendly library (Docker or native)." \
  --add-topic anime \
  --add-topic downloader \
  --add-topic jellyfin \
  --add-topic fastapi \
  --add-topic react \
  --add-topic docker \
  --add-topic yt-dlp \
  --add-topic self-hosted \
  --add-topic anime-sama
```

Do **not** set `--homepage` (leave empty).

- [ ] **Step 2: Verify GitHub About**

Run:

```bash
gh repo view --json description,homepageUrl,repositoryTopics
```

Expected JSON includes the description string above, empty/null homepage, and topics containing at least: `anime`, `downloader`, `jellyfin`, `fastapi`, `react`, `docker`, `yt-dlp`, `self-hosted`, `anime-sama`.

- [ ] **Step 3: Full backend test suite**

Run:

```bash
task test:backend
```

(If `task` is unavailable: `cd backend && uv run pytest -v`.)

Expected: all PASS.

- [ ] **Step 4: Final acceptance sweep (code + product docs)**

Run from repo root:

```bash
rg -n 'DemoAdapter|demo_adapter|demo\.local|adapter_id=["'\'']demo["'\'']|demo-show|solo-demo' \
  backend/src backend/tests frontend/src README.md backend/README.md frontend/README.md \
  || true
```

Expected: no matches.

- [ ] **Step 5: Commit only if Step 1–4 required a local fix**

If Steps 1–4 needed code/doc fixes, commit those fixes. GitHub About itself is remote metadata and does not need a commit. If nothing local changed in this task:

```bash
git status
```

Expected: clean working tree on `chore/remove-demo-and-seo`.

---

## Plan self-review

1. **Spec coverage:** Demo cleanup (frontend + tests + product README) → Tasks 1–2 + Task 3 step 4. Discoverability (GitHub + README + pyproject + package.json) → Tasks 3–4. Branch already created. Historical docs left alone → Global Constraints. Success criteria → Task 4 sweep + tests.
2. **Placeholders:** None; concrete renames, full function bodies, exact `gh`/`pytest` commands.
3. **Consistency:** Neutral titles `fake-show` / `solo-show` / `orphan-show`; adapter id `fake`; unknown host `unknown.local` (not `fake.local`).
