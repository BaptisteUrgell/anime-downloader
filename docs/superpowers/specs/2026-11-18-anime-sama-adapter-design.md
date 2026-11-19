# Anime-Sama Adapter — Design Spec

**Date:** 2026-11-18  
**Status:** Implemented  
**Parent:** [2026-11-17-anime-downloader-design.md](./2026-11-17-anime-downloader-design.md)

## Goals

- `AnimeSamaAdapter` implementing `SourceAdapter`
- Discover episodes from a season URL (`/catalogue/.../saisonN/vostfr/`)
- Resolve media via `GET /api/lien.php?j=<epsJeton>&l=<ID>` then yt-dlp (prefer progressive; remux HLS to mp4)
- Retries: up to 3 per player, skip dead hosts, skip permanent media failures immediately
- In-memory season cache with rediscovery on miss
- **One URL = one season** (no automatic next-season chaining)
- Never re-download `completed` episodes
- Filenames and on-disk layout: see [2026-11-19-jellyfin-library-naming-design.md](./2026-11-19-jellyfin-library-naming-design.md) (supersedes the original slug-lang paths below)

## Superseded path naming (pre–Jellyfin layout)

The first implementation used `library/{slug}-{lang}/{season}/` with filenames `S{ss}E{ee} - {title|series}.{ext}` and `series_title = {slug}-{lang}` (e.g. `dreamland-vostfr`) to keep VOSTFR/VF in separate folders. That layout is obsolete; discovery now uses the display title and release year from the oeuvre page, and a shared path builder applies the Jellyfin TV layout to all adapters.

## Architecture

```
infrastructure/anime_sama/
  provider.py   # HTTP/yt-dlp engine, cache, retries
  adapter.py    # SourceAdapter mapping to domain types
```

`EpisodeRef.source_url` is always the real season page URL.

## Embed resolution

```
GET {origin}/api/lien.php?j={epsJeton}&l={link_id}
Referer: {season_url}
```

## Success criteria

- Preview returns the correct episode count for anime-sama season URLs
- Downloads produce playable `.mp4` (or `.mkv`) files under `./data/library`
- Completed episodes are never re-downloaded
- Unit tests pass without real network calls
