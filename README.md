# anime-downloader

Download a full anime season from a supported URL into a local library: paste a season link, preview the episode count, confirm, then watch progress while files land on disk.

Built for solo / local use (Docker or native). The UI is in French; code and docs are in English.

## Supported adapters

| Adapter ID | Host | Example URL | Notes |
|------------|------|-------------|--------|
| `anime-sama` | `anime-sama.to` (and subdomains) | `https://anime-sama.to/catalogue/hells-paradise/saison1/vostfr/` | Real site. Season page only (one URL = one season). Streams remuxed to `.mp4` when needed. |

Unsupported hosts return a clear “no adapter” error at preview time. More adapters can be added behind the same `SourceAdapter` port.

## Quick start (Docker)

**Requirements:** Docker + Docker Compose.

```bash
docker compose up -d --build
```

Then open **http://localhost:8080**.

- Downloads and SQLite DB are stored under **`./data/`** on your machine (bind-mounted into the container).
- Videos: `./data/library/{Series Title} ({Year})/Season 01/{Series Title} S01E01.mp4` (Jellyfin TV layout)
- Stop: `docker compose down`

Optional, if you use [go-task](https://taskfile.dev):

```bash
task docker:up      # same as compose up -d --build
task docker:logs    # follow logs
task docker:down    # stop
```

## How to use

1. Open the UI at http://localhost:8080.
2. Paste a **season** URL (see adapters above) and leave the field (blur) to preview.
3. Confirm download. Follow season + per-episode progress in the jobs panel.
4. Open files from `./data/library/` in Finder / Explorer (no need to use the app to play them).
5. Re-submitting a season you already finished skips completed episodes.

## Local development (without Docker)

**Requirements:** Node 22+, Python 3.15, [`uv`](https://docs.astral.sh/uv/), [go-task](https://taskfile.dev) recommended.

```bash
# Terminal 1 — API (data under ../data from backend/)
task backend:dev

# Terminal 2 — Vite UI (default http://localhost:5173)
task frontend:dev
```

Useful tasks:

| Task | Purpose |
|------|---------|
| `task --list` | List all tasks |
| `task test:backend` | Run pytest |
| `task api:sync` | Export OpenAPI + regenerate the TypeScript client |
| `task db:migrate` | Apply Alembic migrations |
| `task deps:update` | Upgrade backend + frontend packages |

## Stack

- **Frontend:** Vite, React, TypeScript, Tailwind, shadcn/ui, TanStack Query, Hey API
- **Backend:** FastAPI, DDD layers, SQLAlchemy + Alembic, SQLite, httpx, yt-dlp (+ ffmpeg in the Docker image for HLS)
- **Ops:** Docker Compose (frontend + backend), data bind-mounted to `./data`

## Docs

- Product design: `docs/superpowers/specs/2026-11-17-anime-downloader-design.md`
- Anime-Sama adapter: `docs/superpowers/specs/2026-11-18-anime-sama-adapter-design.md`
- Jellyfin library paths: `docs/superpowers/specs/2026-11-19-jellyfin-library-naming-design.md`
