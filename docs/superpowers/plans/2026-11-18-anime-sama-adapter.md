# Anime-Sama Adapter Implementation Plan

> Historical plan used during implementation. See the design spec for the current contract.

**Goal:** Integrate `AnimeSamaAdapter` so season URLs on `anime-sama.to` preview and download with the best available stream for that season only, skip completed episodes, and write `SxxExx` filenames.

**Architecture:** Thin adapter over `AnimeSamaProvider` (httpx + yt-dlp), domain VOs unchanged, one URL = one season.

**Status:** Implemented on `feat/anime-downloader-mvp`.
