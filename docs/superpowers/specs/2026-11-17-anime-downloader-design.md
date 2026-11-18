# Anime Downloader — Design Spec

**Date:** 2026-11-17  
**Status:** Implemented (MVP)

## 1. Problem

Download a full season of videos from a provided URL for offline playback, without manually stepping through each episode. The app detects the source site, previews the episode count, then downloads and stores content in a local library.

Intended use: solo, local / Docker on the user’s machine. Content only from sources the user is allowed to access.

## 2. Goals (MVP)

- Paste a URL → on blur, discover the season and show the **episode count**
- Confirm → download the whole season
- Local library (series / seasons / episodes, statuses, resume)
- Auto site detection via URL (adapter registry)
- Deployable with Docker: frontend image + backend image + data volume/bind mount

## 3. Non-goals (MVP)

- Built-in video player
- Auth / multi-user
- Many real-site adapters (demo + one real site)
- Multi-worker / Redis / Celery scaling

## 4. Architecture

**FastAPI monolith + in-process worker**, separate frontend.

| Layer | Responsibility | Allowed deps |
|-------|----------------|--------------|
| `domain/` | Entities, VOs, ports, rules | Stdlib only |
| `application/` | Use cases | Domain |
| `infrastructure/` | SQLAlchemy + Alembic, adapters, downloader, worker | Domain + external libs |
| `api/` | FastAPI, Pydantic request/response | Application + Pydantic |

### Ports

- **SourceAdapter** — `matches`, `discover_season`, `resolve_media`, `next_episode`
- **MediaDownloader** — write resolved media to disk (with optional progress callback)
- **LibraryRepository** / **JobRepository**
- **Clock**, **IdGenerator**

### Adapters

1. **DemoAdapter** — demo URLs for design, tests, E2E
2. **AnimeSamaAdapter** — `anime-sama.to` (httpx + yt-dlp)

## 5. Data flow

1. User pastes URL → `POST /jobs/preview` → episode count
2. Confirm → `POST /jobs` → worker downloads sequentially
3. Front polls `GET /jobs` (season progress + per-episode %)
4. Library via `GET /library`
5. On restart, resume incomplete jobs; skip `completed` episodes

### Storage

```
./data/app.db
./data/library/{series}/{season}/S{ss}E{ee} - {title}.{ext}
```

## 6. Success criteria

- `docker compose up` starts front + back
- Preview shows correct episode count
- Season downloads without per-episode manual steps
- Library reflects files under `./data/library`
- Restart does not re-download `completed` episodes
