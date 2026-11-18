# anime-downloader

Download a full anime season from a supported URL (preview on blur → confirm) into a local library. Solo / Docker.

## Stack

- **Frontend:** Vite, React, TypeScript, Tailwind, shadcn/ui, Zod, TanStack Query/Form, **Hey API**
- **Backend:** Python 3.15, FastAPI, DDD, SQLAlchemy + Alembic, SQLite
- **Ops:** Docker Compose (2 images) + [go-task](https://taskfile.dev) (`Taskfile.yml`)

## Prerequisites

- Docker + Docker Compose
- [go-task](https://taskfile.dev/installation/) (`brew install go-task`)
- For local dev: Node 22+, `uv`, Python 3.15

## Commands (`task`)

```bash
task --list
```

| Task | Purpose |
|------|---------|
| `task docker:up` | Start the stack (build if needed) |
| `task docker:update` | Rebuild / recreate images |
| `task docker:down` | Stop the stack |
| `task db:migrate` | Alembic migrations (`upgrade head`) |
| `task deps:backend` | Upgrade Python packages (`uv`) |
| `task deps:frontend` | Upgrade npm packages |
| `task deps:update` | Backend + frontend |
| `task api:sync` | Export OpenAPI + generate Hey API client |
| `task backend:dev` | Uvicorn reload (local) |
| `task frontend:dev` | Vite (local) |
| `task test:backend` | Pytest |

Docker UI: http://localhost:8080  
Demo URL: `https://demo.local/season/demo-show/1`  
Downloads (Docker bind mount): `./data/library/`

## Local development (without Docker)

```bash
task backend:dev    # terminal 1
task frontend:dev   # terminal 2
task api:sync       # after API changes
```

## Docs

- Design: `docs/superpowers/specs/2026-11-17-anime-downloader-design.md`
- Anime-Sama adapter: `docs/superpowers/specs/2026-11-18-anime-sama-adapter-design.md`
