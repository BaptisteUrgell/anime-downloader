# Remove Demo Vestiges & Repo Discoverability — Design Spec

**Date:** 2026-11-19  
**Status:** Approved  
**Branch:** `chore/remove-demo-and-seo`  
**Parent:** [2026-11-19-jellyfin-library-naming-design.md](./2026-11-19-jellyfin-library-naming-design.md)

## Goals

- Remove remaining demo-related surfaces so the product and tests no longer look like a demo-adapter app
- Fill GitHub and in-repo metadata (English) so the public repo is easy to find and understand
- Work on a dedicated branch from `main`

## Non-goals

- Rewriting historical design/plan docs under `docs/superpowers/` that mention `DemoAdapter`
- Heavy web SEO (HTML meta tags, marketing badges, homepage site)
- Product behavior changes (adapters, Jellyfin paths, download UX)

## Context

Production `DemoAdapter` was already removed with Jellyfin library naming. Leftovers still exist:

- Frontend `JobsPanel` still parses legacy `/season/{slug}/{n}` URLs (demo-era path shape)
- Tests still use `adapter_id="demo"`, titles like `demo-show` / `solo-demo`, and at least one `demo.local` URL
- GitHub About is empty (no description, no topics)
- `pyproject.toml` / frontend `package.json` lack a public `description`

Root `README.md` already documents only the Anime-Sama adapter; re-verify during implementation.

## Approach

Minimal cleanup + discoverability pack (approved): scrub active demo vestiges in code/tests/product docs, leave historical specs/plans alone, add English GitHub + package/README metadata.

## Demo cleanup

### Frontend

In `frontend/src/components/JobsPanel.tsx` (`parseJobSeasonLabel`):

- Delete the `/season/([^/]+)/(\d+)/` branch (legacy demo URL shape)
- Keep Anime-Sama `/catalogue/{slug}/saison{N}` parsing
- Keep fallback: raw `sourceUrl` as title when no pattern matches

### Backend / tests

- Rename remaining demo-flavored fixtures to neutral names:
  - `adapter_id="demo"` → e.g. `"fake"` or the fake adapter id already used by `FakeSeasonAdapter`
  - Series titles `demo-show`, `solo-demo` → neutral titles (e.g. `fake-show`, `solo-show`)
  - Any `https://demo.local/...` → `https://fake.local/...` (or another non-demo host already used in that test)
- Delete tests that only existed to cover `DemoAdapter` and have no remaining value under `FakeSeasonAdapter` / Anime-Sama fixtures
- Do **not** reintroduce a production demo adapter

### Product docs

- Ensure root `README.md` (and short package READMEs if they mention adapters) have **no** demo adapter section or example
- Do not edit historical `docs/superpowers/specs|plans` for wording scrub

### Acceptance sweep

After changes, these must match nothing in `backend/src`, `backend/tests`, `frontend/src`, and root/product READMEs:

- `DemoAdapter`
- `demo_adapter`
- `demo.local`
- `adapter_id="demo"` / `adapter_id='demo'`
- Fixture titles / path segments `demo-show`, `solo-demo`
- User-facing copy that presents a “demo” adapter as supported

Historical files under `docs/superpowers/` are exempt. Occurrences of the English word “demo” inside those exempt docs, or unrelated words (e.g. package lock hashes), do not count.

## Discoverability (English)

### GitHub repository About

Set via `gh repo edit` (or equivalent):

| Field | Value |
|-------|--------|
| Description | `Download anime seasons from supported URLs into a local Jellyfin-friendly library (Docker or native).` |
| Homepage | leave empty (local app; no public site) |
| Topics | `anime`, `downloader`, `jellyfin`, `fastapi`, `react`, `docker`, `yt-dlp`, `self-hosted`, `anime-sama` |

Verify with `gh repo view --json description,repositoryTopics,homepageUrl`.

### In-repo metadata

- Root `README.md`: keep structure; strengthen the opening paragraph for search (what it does, local/self-hosted, Jellyfin layout, Anime-Sama). No change to quick-start commands unless a demo mention appears.
- `backend/pyproject.toml`: add `[project].description` matching the GitHub one-liner (or a slightly shorter variant).
- `frontend/package.json`: add `"description"` for the UI package (short English string).

No HTML meta SEO pass; `frontend/index.html` title can stay as-is.

## Branch & delivery

1. Create `chore/remove-demo-and-seo` from up-to-date `main`
2. Apply demo scrub + metadata edits
3. Run backend tests; fix until green
4. Apply GitHub About fields
5. Open PR when implementation plan is executed

## Testing

- `task test:backend` (or `cd backend && uv run pytest`) must pass after renames/deletes
- Manual spot-check: job labels for Anime-Sama URLs still show humanized title + season
- No new E2E required

## Success criteria

- No active demo adapter surface in code, tests, or product README
- GitHub description + topics set in English
- `pyproject.toml` (and frontend `package.json`) have descriptions
- Backend tests green on the branch
