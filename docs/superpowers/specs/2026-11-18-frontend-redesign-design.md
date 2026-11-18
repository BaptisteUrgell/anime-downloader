# Frontend Redesign — Design Spec

**Date:** 2026-11-18  
**Status:** Approved  
**Parent:** [2026-11-17-anime-downloader-design.md](./2026-11-17-anime-downloader-design.md)  
**Source mockup:** root `Anime Downloader.html` (Claude artifact; **delete after implementation**)

## Goals

- Restyle the existing React UI to match the provided mockup (layout, typography, light/dark tokens, badges, empty states)
- Keep current API flows (preview, create job, list jobs, library, retry-failed)
- Add small mockup UI features: theme toggle, dismiss job, “Fermer les terminées”, collapsible library series
- Soft-delete (archive) jobs via new backend endpoints so dismiss survives refresh
- Ship on a dedicated branch from `main`; remove the HTML mockup file when done

## Non-goals

- Accent color picker from the mockup props panel
- Hard-delete of jobs
- Redesigning backend download/worker behavior beyond job dismissal
- Keeping the mockup HTML in the repository

## Decisions

| Topic | Choice |
|-------|--------|
| Scope | Restyle + mockup UI extras, same core product behavior |
| Stack approach | Reskin shadcn/Tailwind (tokens + layout), keep TanStack Query |
| Theme | Light + dark tokens from mockup; toggle in header |
| Theme default | `prefers-color-scheme` on first visit, then persist toggle in `localStorage` |
| Dismiss semantics | Soft-delete via `jobs.dismissed_at` |
| Clear completed | Archive `completed` only; `failed` stay until per-job dismiss or retry |
| Mockup file | Delete after implementation |

## Architecture

```
frontend/
  index.css              # light + .dark CSS variables (mockup tokens)
  App.tsx                # header + layout shell + theme provider
  components/
    UrlDownloadForm.tsx  # “Ajouter une saison” card
    JobsPanel.tsx        # tasks column + dismiss actions
    LibraryPanel.tsx     # collapsible series / seasons
    ThemeToggle.tsx      # optional small extract
backend/
  alembic/...            # jobs.dismissed_at migration
  domain / application   # dismiss_job, dismiss_completed_jobs
  api/routes_jobs.py     # new endpoints
  infrastructure/...     # repo filter + update dismissed_at
```

OpenAPI client regenerated after backend route changes.

## UI

### Tokens & typography

- Fonts: Inter (body), Manrope (titles), JetBrains Mono (URLs / counters)
- Map mockup token sets into CSS variables for light and `.dark` (page, card, ink, soft, muted, border, accent, live, ok/err, badges)
- `color-scheme` follows active theme

### Layout

1. Sticky/simple header: logo mark + “Anime Downloader”, live refresh indicator when a job is pending/running, theme toggle
2. Primary card: eyebrow “NOUVEAU TÉLÉCHARGEMENT”, title “Ajouter une saison”, URL field + pill CTA, preview status strip
3. Two-column main (stack on mobile): **Tâches** | **Bibliothèque**

### Jobs column

- Count + “Fermer les terminées” when ≥1 non-dismissed `completed` job
- Job cards: title/season, mono URL, status badge, season progress bar, optional current-episode progress, error strip + retry, adapter line
- Dismiss (X) on `completed` / `failed` only
- Empty state dashed card when no visible jobs

### Library column

- Summary counts (series · episodes on disk)
- Series rows: initials tile, meta, status badge, expand/collapse
- Expanded: seasons, episode strip, episode rows (number, title, path/error, badge); long runs may use a grouped “Afficher” row as in the mockup when useful

## Data / API

### Schema

- Add nullable `jobs.dismissed_at` (ISO timestamp / timezone-aware UTC)

### Endpoints

| Method | Path | Behavior |
|--------|------|----------|
| `POST` | `/jobs/{id}/dismiss` | Set `dismissed_at` now; **409** if status is `pending` or `running`; **404** if missing |
| `POST` | `/jobs/dismiss-completed` | Soft-dismiss all non-dismissed `completed` jobs; return `{ dismissed_count: n }` |
| `GET` | `/jobs` | Exclude rows with `dismissed_at IS NOT NULL` |

`getJob` may still return a dismissed job by id (useful for debugging); list is UI-facing and filtered.

### Frontend wiring

- Mutations invalidate `listJobs` (and library when retry succeeds, unchanged)
- Theme: read `prefers-color-scheme` if no stored preference; toggle writes `localStorage`

## Error handling

- Existing FR error strings for preview/create/retry, restyled to match mockup error strip
- Dismiss 404 → inline/toast “Tâche introuvable”
- Dismiss 409 → “Impossible de fermer une tâche en cours”
- Corrupt theme preference → fall back to system/light without crashing

## Testing

- Alembic migration applies cleanly
- Repo: list excludes dismissed; dismiss active job rejected
- API: dismiss / dismiss-completed / 409 / 404
- Manual UI check: light/dark, layout, dismiss, clear completed, collapse library

## Success criteria

1. Light and dark UI match the mockup structure and tokens (not necessarily pixel-identical on every spacing)
2. Soft-delete job APIs work; OpenAPI client regenerated
3. Theme toggle respects system default then persistence
4. Backend dismiss tests pass
5. Root `Anime Downloader.html` removed
6. Work delivered on a feature branch from updated `main`
