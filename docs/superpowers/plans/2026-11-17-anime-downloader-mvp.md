# Anime Downloader MVP Implementation Plan

> Historical plan used during MVP implementation. See the design specs for the current architecture.

**Goal:** Ship a solo Dockerized app: paste URL → preview episode count → download a full season into a local library.

**Architecture:** FastAPI monolith with in-process sequential worker; domain ports for `SourceAdapter` / repos; DemoAdapter + AnimeSamaAdapter; Vite React frontend via Hey API.

**Status:** Implemented on `feat/anime-downloader-mvp`.
