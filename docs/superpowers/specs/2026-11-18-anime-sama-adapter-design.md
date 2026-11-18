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
- Filenames: `S{ss}E{ee} - {title|series}.{ext}` under `library/{series}/{season}/`
- `series_title = {slug}-{lang}` (e.g. `dreamland-vostfr`) to avoid VOSTFR/VF collisions

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
