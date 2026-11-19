# Jellyfin Library Naming — Design Spec

**Date:** 2026-11-19  
**Status:** Approved  
**Branch:** `feat/jellyfin-library-naming`  
**Parent:** [2026-11-18-anime-sama-adapter-design.md](./2026-11-18-anime-sama-adapter-design.md)

## Goals

- Standardize on-disk library layout for Jellyfin TV shows metadata matching
- Anime-Sama discovery uses the human series title plus release year from the oeuvre page
- Same path layout for every adapter (single path builder)
- Migrate existing downloads from the old slug-lang layout
- Remove the demo adapter entirely

## Non-goals

- Adding AniList/TMDB/MAL IDs into folder names (year + title is enough for now)
- Keeping VOSTFR and VF as separate series folders
- Language tags in episode filenames

## Target layout (Jellyfin TV)

```text
library/{Series Title} ({Year|Unknown})/Season {NN}/{Series Title} S{NN}E{EE}.{ext}
```

Example:

```text
library/Hell's Paradise (2023)/Season 01/Hell's Paradise S01E01.mp4
```

Rules:

- Series folder = display title + `(Year)` or `(Unknown)` if year missing
- Season folder = `Season {NN}` with zero-padding (`Season 01`, not `Season 1`)
- Episode file = `{Series Title} S{NN}E{EE}.{ext}` (no language suffix)
- Re-download of the same episode (any language URL) writes the same path and overwrites

## Architecture

### Domain

- Extend `SeasonDiscovery` with `release_year: int | None`
- `series_title` becomes the **display title** (e.g. `Hell's Paradise`), not `{slug}-{lang}`
- Extend `Series` with `release_year: int | None`
- Alembic migration: add nullable `release_year` on `series`; change uniqueness from `title` alone to `(title, release_year)` so two works with the same name and different years do not collide (`NULL` year treated as distinct unknown bucket per DB rules — application treats missing year as the shared `(Unknown)` folder)

### Shared path builder

Single helper used by the worker (and migration) for all adapters:

```text
library_root / f"{title} ({year_or_unknown})" / f"Season {season:02d}" / f"{title} S{season:02d}E{episode:02d}.{ext}"
```

Sanitize path segments only for filesystem-illegal characters (`/`, `\`, NUL); keep apostrophes and spaces so Jellyfin can match titles.

### Anime-Sama adapter

Given a season URL such as  
`https://anime-sama.to/catalogue/hells-paradise/saison1/vostfr/`:

1. Parse slug + season number from the URL (`saisonN` → `N`)
2. Fetch oeuvre page `/catalogue/{slug}/`
3. Read display title from `#titreOeuvre`
4. Read year from `.oe-meta` (first token before `·`, e.g. `2023`); if missing → `None`
5. Return `SeasonDiscovery(series_title=…, release_year=…, season_number=…, episodes=…)`

If the oeuvre page cannot be fetched or the title cannot be parsed, discovery fails (do not fall back to slug-lang titles).

### Worker

- Upsert `Series` with display title + year (match key: title + release_year)
- Build destination via the shared path builder
- Skip download when episode status is `completed` and the file exists at the expected path (existing behavior)
- When a download does run to that path (retry of failed/missing file, or new job after status reset), overwrite the file if present
- VOSTFR and VF season URLs for the same work resolve to the same series folder and the same episode path → last successful download wins

### Demo adapter removal

- Delete `demo_adapter.py` and unregister it from `AdapterRegistry` / `deps.py`
- Rewrite tests that used `demo.local` to use fakes/stubs or anime-sama fixtures
- Remove `test_demo_adapter.py`

## Data flow

```text
Source URL
  → Adapter.discover_season
      → (series_title, release_year, season_number, episodes)
  → Upsert Series / Season / Episodes
  → Path builder → destination path
  → Download (overwrite if same path)
```

## Migration of existing library

Run once (worker startup hook or dedicated command), idempotent:

1. For each completed episode with a `file_path`, resolve identity from `source_url` via the matching adapter
2. Compute the new Jellyfin path
3. Create parent dirs; `rename` file into place
4. Update `file_path`, `Series.title`, `Series.release_year`
5. If multiple series rows (e.g. `hells-paradise-vostfr` and `hells-paradise-vf`) map to the same display title + year, merge into one `Series` (reattach seasons/episodes; drop the duplicate series row)
6. If already at the target path → no-op
7. If target already exists during rename → keep target, remove source after size check, log warning
8. Partial failure → log; next run retries remaining items

Old:

```text
library/hells-paradise-vostfr/1/S01E01 - hells-paradise-vostfr.mp4
```

New:

```text
library/Hell's Paradise (2023)/Season 01/Hell's Paradise S01E01.mp4
```

## Error handling

| Case | Behavior |
|------|----------|
| Year missing on oeuvre page | Use `(Unknown)` in folder name |
| Oeuvre page unreachable / title missing | Fail discovery |
| Filesystem rename collision | Keep target, drop source after verification, warn |
| Migration item fails | Log and continue; retry next run |

## Testing

- Path builder: apostrophes, `(Unknown)`, `Season 01` / `S01E01` formatting
- Anime-Sama: oeuvre HTML fixture → `Hell's Paradise` + `2023`; season URL → season number
- Worker: writes under new layout; second download of same episode overwrites same path
- Migration: old layout → new layout + DB updates; second run no-op; vostfr/vf series merge when applicable
- No remaining production dependency on `DemoAdapter` / `demo.local`

## Success criteria

- New downloads land in Jellyfin-standard paths with title + year
- Existing library is migrated without manual renames
- Preview/discovery shows human titles (not slug-lang)
- Demo adapter gone; tests green without it
```
