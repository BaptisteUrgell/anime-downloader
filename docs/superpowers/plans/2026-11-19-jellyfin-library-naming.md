# Jellyfin Library Naming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist downloads in Jellyfin TV layout `Title (Year)/Season NN/Title SxxExx.ext`, source title+year from Anime-Sama oeuvre pages, migrate existing files, and remove the demo adapter.

**Architecture:** Shared path builder used by the worker and a one-shot library migrator; `SeasonDiscovery` / `Series` carry `release_year`; Anime-Sama fetches `/catalogue/{slug}/` for `#titreOeuvre` + year; tests replace `DemoAdapter` with an in-test `FakeSeasonAdapter`.

**Tech Stack:** Python 3, SQLAlchemy, Alembic, httpx mocks, pytest, FastAPI

## Global Constraints

- On-disk layout: `library/{Series Title} ({Year|Unknown})/Season {NN}/{Series Title} S{NN}E{EE}.{ext}`
- Season folders zero-padded (`Season 01`); episode markers `S01E01`
- No language suffix in filenames; same path overwrites
- Missing year → folder uses `(Unknown)`
- Spec: `docs/superpowers/specs/2026-11-19-jellyfin-library-naming-design.md`
- Branch: `feat/jellyfin-library-naming`
- No demo adapter in production registry
- Sanitize only `/`, `\`, NUL in path segments; keep spaces and apostrophes

---

## File structure

| File | Responsibility |
|------|----------------|
| `backend/src/anime_downloader/infrastructure/library_paths.py` | Pure path builder + sanitize |
| `backend/src/anime_downloader/domain/model.py` | `release_year` on `SeasonDiscovery` / `Series` |
| `backend/src/anime_downloader/infrastructure/db/models.py` | `SeriesRow.release_year` + unique `(title, release_year)` |
| `backend/alembic/versions/0003_series_release_year.py` | Schema migration |
| `backend/src/anime_downloader/infrastructure/persistence/library_repository.py` | Upsert/match by title+year; merge helper |
| `backend/src/anime_downloader/infrastructure/anime_sama/provider.py` | Fetch/parse oeuvre meta |
| `backend/src/anime_downloader/infrastructure/anime_sama/adapter.py` | Wire oeuvre meta into discovery |
| `backend/src/anime_downloader/infrastructure/worker.py` | Use path builder; match series by title+year |
| `backend/src/anime_downloader/application/start_season_download.py` | Match/upsert series with year |
| `backend/src/anime_downloader/infrastructure/library_migrator.py` | Rename old layout → Jellyfin + DB updates |
| `backend/src/anime_downloader/api/deps.py` | Registry without demo; drop demo.local downloader branch |
| `backend/src/anime_downloader/api/main.py` | Run migrator after migrations on startup |
| `backend/tests/support/fake_season_adapter.py` | Test-only adapter replacing DemoAdapter |
| Delete: `backend/src/anime_downloader/infrastructure/demo_adapter.py` | |
| Delete: `backend/tests/infrastructure/test_demo_adapter.py` | |

---

### Task 1: Shared path builder

**Files:**
- Create: `backend/src/anime_downloader/infrastructure/library_paths.py`
- Test: `backend/tests/infrastructure/test_library_paths.py`

**Interfaces:**
- Produces: `build_episode_path(library_root: Path, series_title: str, release_year: int | None, season_number: int, episode_number: int, ext: str) -> Path`
- Produces: `sanitize_segment(value: str) -> str`
- Produces: `series_folder_name(series_title: str, release_year: int | None) -> str`
- Produces: `season_folder_name(season_number: int) -> str`
- Produces: `episode_filename(series_title: str, season_number: int, episode_number: int, ext: str) -> str`

- [ ] **Step 1: Write the failing tests**

```python
from pathlib import Path

from anime_downloader.infrastructure.library_paths import (
    build_episode_path,
    episode_filename,
    season_folder_name,
    series_folder_name,
)


def test_series_folder_includes_year():
    assert series_folder_name("Hell's Paradise", 2023) == "Hell's Paradise (2023)"


def test_series_folder_unknown_year():
    assert series_folder_name("Hell's Paradise", None) == "Hell's Paradise (Unknown)"


def test_season_folder_zero_padded():
    assert season_folder_name(1) == "Season 01"
    assert season_folder_name(10) == "Season 10"


def test_episode_filename_jellyfin_style():
    assert (
        episode_filename("Hell's Paradise", 1, 1, "mp4")
        == "Hell's Paradise S01E01.mp4"
    )


def test_build_episode_path_full_layout(tmp_path: Path):
    path = build_episode_path(
        tmp_path,
        "Hell's Paradise",
        2023,
        season_number=1,
        episode_number=1,
        ext="mp4",
    )
    assert path == tmp_path / "Hell's Paradise (2023)" / "Season 01" / "Hell's Paradise S01E01.mp4"


def test_sanitize_keeps_apostrophe_strips_slash():
    from anime_downloader.infrastructure.library_paths import sanitize_segment

    assert sanitize_segment("Hell's Paradise") == "Hell's Paradise"
    assert sanitize_segment("A/B") == "A_B"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/infrastructure/test_library_paths.py -v`  
Expected: FAIL (module not found)

- [ ] **Step 3: Implement `library_paths.py`**

```python
from __future__ import annotations

from pathlib import Path


def sanitize_segment(value: str) -> str:
    cleaned = value.replace("/", "_").replace("\\", "_").replace("\x00", "").strip()
    if cleaned in {"", ".", ".."}:
        return "_"
    return cleaned


def series_folder_name(series_title: str, release_year: int | None) -> str:
    year_label = str(release_year) if release_year is not None else "Unknown"
    return sanitize_segment(f"{series_title} ({year_label})")


def season_folder_name(season_number: int) -> str:
    return f"Season {season_number:02d}"


def episode_filename(
    series_title: str, season_number: int, episode_number: int, ext: str
) -> str:
    safe_title = sanitize_segment(series_title)
    safe_ext = sanitize_segment(ext.lstrip("."))
    return f"{safe_title} S{season_number:02d}E{episode_number:02d}.{safe_ext}"


def build_episode_path(
    library_root: Path,
    series_title: str,
    release_year: int | None,
    season_number: int,
    episode_number: int,
    ext: str,
) -> Path:
    return (
        library_root
        / series_folder_name(series_title, release_year)
        / season_folder_name(season_number)
        / episode_filename(series_title, season_number, episode_number, ext)
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/infrastructure/test_library_paths.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/anime_downloader/infrastructure/library_paths.py \
  backend/tests/infrastructure/test_library_paths.py
git commit -m "$(cat <<'EOF'
Add Jellyfin library path builder.

Centralize Title (Year)/Season NN/Title SxxExx path formatting for all adapters.
EOF
)"
```

---

### Task 2: Domain `release_year` on Series and SeasonDiscovery

**Files:**
- Modify: `backend/src/anime_downloader/domain/model.py`
- Modify: any `SeasonDiscovery(...)` / `Series(...)` call sites that break type-check/tests (minimal fixes so imports compile; full adapter work in later tasks)
- Test: `backend/tests/domain/test_models_release_year.py`

**Interfaces:**
- Produces: `SeasonDiscovery(series_title: str, season_number: int, episodes: tuple[EpisodeRef, ...], release_year: int | None = None)`
- Produces: `Series(id: str, title: str, release_year: int | None = None)`

- [ ] **Step 1: Write the failing test**

```python
from anime_downloader.domain.model import EpisodeRef, SeasonDiscovery, Series


def test_season_discovery_carries_release_year():
    discovery = SeasonDiscovery(
        series_title="Hell's Paradise",
        season_number=1,
        release_year=2023,
        episodes=(EpisodeRef(source_url="https://x", number=1),),
    )
    assert discovery.release_year == 2023


def test_series_carries_release_year():
    series = Series(id="s1", title="Hell's Paradise", release_year=2023)
    assert series.release_year == 2023


def test_release_year_defaults_to_none():
    discovery = SeasonDiscovery(
        series_title="X",
        season_number=1,
        episodes=(),
    )
    assert discovery.release_year is None
    assert Series(id="s", title="X").release_year is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/domain/test_models_release_year.py -v`  
Expected: FAIL (`unexpected keyword` or missing attribute)

- [ ] **Step 3: Update domain models**

In `domain/model.py`:

```python
@dataclass(frozen=True)
class SeasonDiscovery:
    series_title: str
    season_number: int
    episodes: tuple[EpisodeRef, ...]
    release_year: int | None = None

    @property
    def episode_count(self) -> int:
        return len(self.episodes)


@dataclass
class Series:
    id: str
    title: str
    release_year: int | None = None
```

- [ ] **Step 4: Run domain test + full suite smoke**

Run: `cd backend && uv run pytest tests/domain/test_models_release_year.py -v`  
Expected: PASS

Fix any `Series(...)` / `SeasonDiscovery(...)` construction errors that break collection (keep old titles for now; Task 5/6/7 finish behavior).

- [ ] **Step 5: Commit**

```bash
git add backend/src/anime_downloader/domain/model.py \
  backend/tests/domain/test_models_release_year.py
git commit -m "$(cat <<'EOF'
Add release_year to Series and SeasonDiscovery.

Carry display-year metadata through discovery into the library model.
EOF
)"
```

---

### Task 3: DB column + repository match on title+year

**Files:**
- Modify: `backend/src/anime_downloader/infrastructure/db/models.py`
- Create: `backend/alembic/versions/0003_series_release_year.py`
- Modify: `backend/src/anime_downloader/infrastructure/persistence/library_repository.py`
- Modify: `backend/src/anime_downloader/domain/ports.py` (add `delete_series` if merge needs it — or keep merge inside repository)
- Test: `backend/tests/infrastructure/test_sqlalchemy_repos.py` (extend)

**Interfaces:**
- Consumes: `Series(id, title, release_year)`
- Produces: `upsert_series` matches existing row by `(title, release_year)` (NULL year equals NULL)
- Produces: `find_series(title, release_year) -> Series | None` (optional helper) OR keep list+filter in callers
- Produces: `reassign_season_series(season_id, new_series_id)` and `delete_series(series_id)` for migration merge — add only if Task 8 needs them; prefer adding in this task:

```python
def delete_series(self, series_id: str) -> None: ...
def reassign_season(self, season_id: str, new_series_id: str) -> None: ...
```

- [ ] **Step 1: Write failing repository tests**

```python
def test_upsert_series_matches_on_title_and_year(session_factory) -> None:
    repo = SqlAlchemyLibraryRepository(session_factory)
    a = repo.upsert_series(Series(id="s1", title="Hell's Paradise", release_year=2023))
    b = repo.upsert_series(Series(id="s2", title="Hell's Paradise", release_year=2023))
    assert a.id == b.id == "s1"  # second upsert finds by title+year, keeps first id
    # OR: if upsert by id wins when id differs, document: callers always resolve id first.
```

Prefer the existing pattern: callers resolve `existing_series` first; repository upsert by id updates title/year, and lookup-by-title becomes lookup-by-title+year when inserting without known id.

Update `_to_series` and insert paths:

```python
def test_series_persists_release_year(session_factory) -> None:
    repo = SqlAlchemyLibraryRepository(session_factory)
    saved = repo.upsert_series(
        Series(id="s1", title="Hell's Paradise", release_year=2023)
    )
    assert saved.release_year == 2023
    listed = repo.list_series()
    assert listed[0].release_year == 2023


def test_two_years_are_distinct_series(session_factory) -> None:
    repo = SqlAlchemyLibraryRepository(session_factory)
    repo.upsert_series(Series(id="s1", title="Show", release_year=2020))
    repo.upsert_series(Series(id="s2", title="Show", release_year=2021))
    assert {s.id for s in repo.list_series()} == {"s1", "s2"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/infrastructure/test_sqlalchemy_repos.py::test_series_persists_release_year tests/infrastructure/test_sqlalchemy_repos.py::test_two_years_are_distinct_series -v`  
Expected: FAIL

- [ ] **Step 3: Alembic migration `0003_series_release_year.py`**

```python
"""Add series.release_year; unique (title, release_year).

Revision ID: 0003_series_release_year
Revises: 0002_jobs_dismissed_at
Create Date: 2026-11-19 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0003_series_release_year"
down_revision: str | None = "0002_jobs_dismissed_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("series") as batch:
        batch.add_column(sa.Column("release_year", sa.Integer(), nullable=True))
        batch.drop_constraint("title", type_="unique")
        batch.create_unique_constraint(
            "uq_series_title_release_year", ["title", "release_year"]
        )


def downgrade() -> None:
    with op.batch_alter_table("series") as batch:
        batch.drop_constraint("uq_series_title_release_year", type_="unique")
        batch.create_unique_constraint("title", ["title"])
        batch.drop_column("release_year")
```

Note: SQLite unique constraint name on title may be `title` or auto-named — inspect `0001_initial_schema` / live DB and adjust `drop_constraint` name to match (`UniqueConstraint("title")` → often `title` or `uq_series_title`).

- [ ] **Step 4: Update `SeriesRow` + repository**

```python
class SeriesRow(Base):
    __tablename__ = "series"
    __table_args__ = (
        UniqueConstraint("title", "release_year", name="uq_series_title_release_year"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    release_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
```

In `upsert_series`:
- If row by id exists → update `title` and `release_year`
- Else look up `title == …` AND (`release_year == …` OR both NULL)
- Else insert with both fields

```python
def _to_series(row: SeriesRow) -> Series:
    return Series(id=row.id, title=row.title, release_year=row.release_year)
```

Add to port + repo for Task 8:

```python
def delete_series(self, series_id: str) -> None:
    with self._session_factory() as session:
        row = session.get(SeriesRow, series_id)
        if row is not None:
            session.delete(row)
            session.commit()


def reassign_season(self, season_id: str, new_series_id: str) -> None:
    with self._session_factory() as session:
        row = session.get(SeasonRow, season_id)
        if row is None:
            return
        row.series_id = new_series_id
        session.commit()
```

- [ ] **Step 5: Run repository tests**

Run: `cd backend && uv run pytest tests/infrastructure/test_sqlalchemy_repos.py -v`  
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/0003_series_release_year.py \
  backend/src/anime_downloader/infrastructure/db/models.py \
  backend/src/anime_downloader/infrastructure/persistence/library_repository.py \
  backend/src/anime_downloader/domain/ports.py \
  backend/tests/infrastructure/test_sqlalchemy_repos.py
git commit -m "$(cat <<'EOF'
Persist series release_year with title+year uniqueness.

Enable Jellyfin folder identity and series merge during migration.
EOF
)"
```

---

### Task 4: Match series by title+year in start + worker

**Files:**
- Modify: `backend/src/anime_downloader/application/start_season_download.py`
- Modify: `backend/src/anime_downloader/infrastructure/worker.py` (series lookup only; path builder in Task 6)
- Test: extend `backend/tests/application/test_start_season_download.py` with a stub adapter that returns `release_year`

**Interfaces:**
- Consumes: `SeasonDiscovery.release_year`
- Produces: series upsert `Series(..., release_year=discovery.release_year)`
- Match predicate:

```python
def _same_series(a_title, a_year, b_title, b_year) -> bool:
    return a_title == b_title and a_year == b_year
```

- [ ] **Step 1: Write failing test**

Use a tiny stub adapter in the test file (not DemoAdapter):

```python
class _YearAdapter:
    @property
    def adapter_id(self) -> str:
        return "year-stub"

    def matches(self, url: SourceUrl) -> bool:
        return url.host == "year.local"

    def discover_season(self, url: SourceUrl) -> SeasonDiscovery:
        return SeasonDiscovery(
            series_title="Hell's Paradise",
            season_number=1,
            release_year=2023,
            episodes=(
                EpisodeRef(source_url=url.value + "/e/1", number=1),
            ),
        )

    def resolve_media(self, episode: EpisodeRef) -> MediaLocator:
        return MediaLocator(url="https://year.local/media/1.mp4")

    def next_episode(self, episode: EpisodeRef) -> EpisodeRef | None:
        return None


def test_start_season_download_stores_release_year(...):
    # registry with _YearAdapter, call start_season_download
    # assert library.list_series()[0].release_year == 2023
```

- [ ] **Step 2: Run test — expect FAIL** (year not stored / match ignores year)

- [ ] **Step 3: Update matching + upsert**

In `start_season_download.py` and `worker.py`:

```python
existing_series = next(
    (
        s
        for s in library.list_series()
        if s.title == discovery.series_title
        and s.release_year == discovery.release_year
    ),
    None,
)
series = library.upsert_series(
    Series(
        id=series_id,
        title=discovery.series_title,
        release_year=discovery.release_year,
    )
)
```

- [ ] **Step 4: Run tests**

Run: `cd backend && uv run pytest tests/application/test_start_season_download.py -v`  
Expected: PASS for the new test (other tests may still use DemoAdapter until Task 7)

- [ ] **Step 5: Commit**

```bash
git add backend/src/anime_downloader/application/start_season_download.py \
  backend/src/anime_downloader/infrastructure/worker.py \
  backend/tests/application/test_start_season_download.py
git commit -m "$(cat <<'EOF'
Match and persist library series by title and release year.

Keep VOSTFR/VF jobs collapsing onto one Series identity.
EOF
)"
```

---

### Task 5: Anime-Sama oeuvre title + year

**Files:**
- Modify: `backend/src/anime_downloader/infrastructure/anime_sama/provider.py`
- Modify: `backend/src/anime_downloader/infrastructure/anime_sama/adapter.py`
- Create: `backend/tests/infrastructure/anime_sama/fixtures/oeuvre_page.html` (minimal excerpt from user HTML: `#titreOeuvre` + `.oe-meta`)
- Modify: `backend/tests/infrastructure/anime_sama/test_adapter.py`
- Test: `backend/tests/infrastructure/anime_sama/test_provider.py` (oeuvre parse)

**Interfaces:**
- Produces: `AnimeSamaProvider.fetch_oeuvre_meta(catalogue_url_or_slug) -> tuple[str, int | None]`
- Consumes: season URL → derive `https://{host}/catalogue/{slug}/`
- Adapter `discover_season` returns display title + year

- [ ] **Step 1: Write failing tests**

Fixture `oeuvre_page.html` (minimal):

```html
<h1 id="titreOeuvre" class="oe-titre">Hell's Paradise</h1>
<p class="oe-meta">2023<span class="oe-point">·</span>Série TV<span class="oe-point">·</span>MAPPA</p>
```

```python
def test_fetch_oeuvre_meta_parses_title_and_year():
    # MockTransport returns oeuvre_page.html for /catalogue/hells-paradise/
    title, year = provider.fetch_oeuvre_meta(
        "https://anime-sama.to/catalogue/hells-paradise/"
    )
    assert title == "Hell's Paradise"
    assert year == 2023


def test_adapter_discover_uses_oeuvre_title_and_year():
    # Mock: season page + oeuvre page
    discovery = adapter.discover_season(SourceUrl.parse(
        "https://anime-sama.to/catalogue/hells-paradise/saison1/vostfr/"
    ))
    assert discovery.series_title == "Hell's Paradise"
    assert discovery.release_year == 2023
    assert discovery.season_number == 1
```

Also test: missing `#titreOeuvre` → raises `AnimeSamaError`; missing year → `release_year is None`.

- [ ] **Step 2: Run tests — expect FAIL**

- [ ] **Step 3: Implement parse + fetch**

In provider:

```python
TITRE_OEUVRE_RE = re.compile(
    r'id=["\']titreOeuvre["\'][^>]*>([^<]+)<', re.IGNORECASE
)
OE_META_YEAR_RE = re.compile(
    r'class=["\']oe-meta["\'][^>]*>\s*(\d{4})\b', re.IGNORECASE
)

def fetch_oeuvre_meta(self, oeuvre_url: str) -> tuple[str, int | None]:
    response = self.client.get(oeuvre_url)
    response.raise_for_status()
    html = response.text
    title_match = TITRE_OEUVRE_RE.search(html)
    if title_match is None:
        raise AnimeSamaError(f"Missing titreOeuvre on {oeuvre_url}")
    title = title_match.group(1).strip()
    year_match = OE_META_YEAR_RE.search(html)
    year = int(year_match.group(1)) if year_match else None
    return title, year
```

In adapter `_parse_season_meta` → return `(slug, season_number, lang_ignored)`; build oeuvre URL; call `fetch_oeuvre_meta`; pass into `SeasonDiscovery`.

```python
def discover_season(self, url: SourceUrl) -> SeasonDiscovery:
    episodes = self._provider.discover_season(url.value)
    slug, season_number = _parse_slug_and_season(url.value)
    oeuvre_url = _oeuvre_url(url.value, slug)
    title, year = self._provider.fetch_oeuvre_meta(oeuvre_url)
    return SeasonDiscovery(
        series_title=title,
        release_year=year,
        season_number=season_number,
        episodes=tuple(...),
    )
```

- [ ] **Step 4: Run anime_sama tests**

Run: `cd backend && uv run pytest tests/infrastructure/anime_sama/ -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/anime_downloader/infrastructure/anime_sama/ \
  backend/tests/infrastructure/anime_sama/
git commit -m "$(cat <<'EOF'
Resolve Anime-Sama series title and year from oeuvre pages.

Replace slug-lang series_title with Jellyfin-friendly display metadata.
EOF
)"
```

---

### Task 6: Worker writes Jellyfin paths

**Files:**
- Modify: `backend/src/anime_downloader/infrastructure/worker.py`
- Modify: `backend/tests/infrastructure/test_worker.py`
- Modify: path assertions in `backend/tests/api/test_jobs_api.py` (if still using old layout after Task 7)

**Interfaces:**
- Consumes: `build_episode_path`, `Series.release_year`
- Replaces `_build_destination_path` body

- [ ] **Step 1: Write / update failing worker assertion**

With stub adapter title `Hell's Paradise`, year `2023`, episode 1:

```python
expected = (
    library_root
    / "Hell's Paradise (2023)"
    / "Season 01"
    / "Hell's Paradise S01E01.mp4"
)
assert expected.is_file()
```

Episode title must **not** change the filename (Jellyfin base name is series + SxxExx only).

- [ ] **Step 2: Run focused worker test — expect FAIL** (old path)

- [ ] **Step 3: Implement destination path**

```python
from anime_downloader.infrastructure.library_paths import build_episode_path

def _build_destination_path(...):
    ext = _extract_extension(media)
    return build_episode_path(
        self._library_root,
        series.title,
        series.release_year,
        season.number,
        episode.number,
        ext,
    )
```

Remove old `SxxExx - {title}` logic. Keep `_sanitize_segment` only if still used by `_extract_extension`, or import `sanitize_segment` from `library_paths`.

- [ ] **Step 4: Run worker tests**

Run: `cd backend && uv run pytest tests/infrastructure/test_worker.py -v`  
Expected: PASS for path-related tests (DemoAdapter tests may still fail until Task 7)

- [ ] **Step 5: Commit**

```bash
git add backend/src/anime_downloader/infrastructure/worker.py \
  backend/tests/infrastructure/test_worker.py
git commit -m "$(cat <<'EOF'
Write downloads using Jellyfin Title (Year)/Season NN paths.

Stop using slug-lang folders and SxxExx - title filenames.
EOF
)"
```

---

### Task 7: Remove DemoAdapter; introduce FakeSeasonAdapter for tests

**Files:**
- Delete: `backend/src/anime_downloader/infrastructure/demo_adapter.py`
- Delete: `backend/tests/infrastructure/test_demo_adapter.py`
- Create: `backend/tests/support/fake_season_adapter.py`
- Create: `backend/tests/support/__init__.py` (empty)
- Modify: `backend/src/anime_downloader/api/deps.py` — registry + drop `demo.local` branch in `DefaultMediaDownloader`
- Modify: all tests importing `DemoAdapter` / `demo.local` URLs:
  - `backend/tests/api/test_jobs_api.py`
  - `backend/tests/application/test_start_season_download.py`
  - `backend/tests/application/test_preview_season.py`
  - `backend/tests/infrastructure/test_worker.py`
  - `backend/tests/infrastructure/test_sqlalchemy_repos.py` (URLs can stay as opaque strings)
  - `backend/tests/application/test_dismiss_job.py`
  - `backend/tests/infrastructure/test_yt_dlp_downloader.py` if it references demo downloader kwarg

**Interfaces:**
- Produces test helper:

```python
# tests/support/fake_season_adapter.py
class FakeSeasonAdapter:
    def __init__(self, episode_count: int = 3, release_year: int | None = 2020) -> None:
        self._episode_count = episode_count
        self._release_year = release_year

    @property
    def adapter_id(self) -> str:
        return "fake"

    def matches(self, url: SourceUrl) -> bool:
        return url.host == "fake.local"

    def discover_season(self, url: SourceUrl) -> SeasonDiscovery:
        series_title, season_number = _parse(url)  # /season/{title}/{n}
        base = f"https://fake.local/season/{series_title}/{season_number}"
        episodes = tuple(
            EpisodeRef(source_url=f"{base}/e/{n}", number=n)
            for n in range(1, self._episode_count + 1)
        )
        return SeasonDiscovery(
            series_title=series_title,
            season_number=season_number,
            release_year=self._release_year,
            episodes=episodes,
        )

    def resolve_media(self, episode: EpisodeRef) -> MediaLocator:
        return MediaLocator(
            url=f"https://fake.local/media/{episode.number}.mp4",
            suggested_filename=f"E{episode.number:02d}.mp4",
        )
    # next_episode like former DemoAdapter
```

- Production: `build_default_registry() -> AdapterRegistry([AnimeSamaAdapter()])`
- Tests that need downloads: `create_app(tmp_path, registry=AdapterRegistry([FakeSeasonAdapter()]), downloader=FakeMediaDownloader())`

- [ ] **Step 1: Add FakeSeasonAdapter + rewrite one API test; delete demo module**

Update `test_preview_season_returns_...` to inject fake registry and assert title/year.

Remove `demo.local` special case from `DefaultMediaDownloader` (and `demo_downloader` param if unused).

- [ ] **Step 2: Run full test suite; fix remaining DemoAdapter imports**

Run: `cd backend && uv run pytest -v`  
Expected: failures only where DemoAdapter still referenced — fix until green.

Path expectations become:

```python
tmp_path / "library" / "solo-demo (2020)" / "Season 01" / "solo-demo S01E01.mp4"
```

(with `FakeSeasonAdapter(release_year=2020)`).

- [ ] **Step 3: Confirm no production demo references**

Run: `cd backend && rg -n "DemoAdapter|demo\\.local|demo_adapter" src tests || true`  
Expected: only possibly opaque historical URLs in repo unit tests that do not resolve adapters; prefer zero matches in `src/`.

- [ ] **Step 4: Commit**

```bash
git add -A backend/src/anime_downloader/infrastructure/demo_adapter.py \
  backend/tests/infrastructure/test_demo_adapter.py \
  backend/tests/support/ \
  backend/src/anime_downloader/api/deps.py \
  backend/tests/
git commit -m "$(cat <<'EOF'
Remove DemoAdapter and switch tests to FakeSeasonAdapter.

Keep production registry anime-sama-only; inject fakes in tests.
EOF
)"
```

---

### Task 8: Library migrator (old layout → Jellyfin)

**Files:**
- Create: `backend/src/anime_downloader/infrastructure/library_migrator.py`
- Test: `backend/tests/infrastructure/test_library_migrator.py`
- Modify: `backend/src/anime_downloader/api/main.py` (call after `run_migrations` / on lifespan)
- Modify: `backend/src/anime_downloader/api/deps.py` or `build_container` to expose migrator inputs

**Interfaces:**
- Produces:

```python
def migrate_library(
    *,
    library: LibraryRepository,
    registry: AdapterRegistry,
    library_root: Path,
) -> MigrationReport:  # renamed_files: int, merged_series: int, errors: list[str]
```

Algorithm (idempotent):

1. For each series → seasons → episodes with `status == completed` and `file_path`
2. `adapter = registry.resolve(SourceUrl.parse(episode.source_url))` — skip/log if unknown host (legacy demo paths)
3. `discovery = adapter.discover_season(SourceUrl.parse(season_url_from_episode))`  
   For anime-sama, `episode.source_url` is already the season URL
4. Compute `new_path = build_episode_path(library_root, discovery.series_title, discovery.release_year, season.number, episode.number, ext_from_old_path)`
5. If `Path(episode.file_path).resolve() == new_path.resolve()`: ensure series title/year updated; continue
6. Else: `new_path.parent.mkdir(parents=True)`; if `new_path.exists()` and different from source → keep target, unlink source after size check; else `Path(old).replace(new_path)`
7. `upsert_episode` with new `file_path`
8. Update series to discovery title/year; if another series already has that identity, `reassign_season` then `delete_series` empty duplicate
9. After file moves, prune empty old directories under `library_root`

- [ ] **Step 1: Write failing migrator test with FakeSeasonAdapter**

```python
def test_migrates_old_slug_layout_to_jellyfin(tmp_path, session_factory):
    # Arrange: Series title hells-paradise-vostfr, season 1, episode file at
    # library/hells-paradise-vostfr/1/S01E01 - hells-paradise-vostfr.mp4
    # source_url that FakeSeasonAdapter maps to title "Hell's Paradise", year 2023
    # Act: migrate_library(...)
    # Assert: new path exists, old gone, DB file_path + series title/year updated
```

Also: `test_migrate_is_idempotent`, `test_merge_duplicate_series_same_title_year`.

For FakeSeasonAdapter, use a URL scheme the fake understands, **or** a dedicated `_MigrationStubAdapter` in the test that returns fixed meta from any URL while files sit in old folders.

Prefer a stub in the migrator test so it does not need network:

```python
class _MetaAdapter:
    def discover_season(self, url):
        return SeasonDiscovery(
            series_title="Hell's Paradise",
            release_year=2023,
            season_number=1,
            episodes=(EpisodeRef(source_url=url.value, number=1),),
        )
    # matches always true for test host
```

- [ ] **Step 2: Run test — expect FAIL**

- [ ] **Step 3: Implement migrator**

Keep functions small: `_plan_move`, `_merge_series_if_needed`, `migrate_library`.

- [ ] **Step 4: Wire on startup**

In `create_app` lifespan after container init (before or after `resume_incomplete`):

```python
from anime_downloader.infrastructure.library_migrator import migrate_library

migrate_library(
    library=container.library,
    registry=container.registry,
    library_root=container.data_dir / "library",
)
```

Log the `MigrationReport` at info level.

- [ ] **Step 5: Run migrator + full suite**

Run: `cd backend && uv run pytest tests/infrastructure/test_library_migrator.py -v && uv run pytest -v`  
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/src/anime_downloader/infrastructure/library_migrator.py \
  backend/tests/infrastructure/test_library_migrator.py \
  backend/src/anime_downloader/api/main.py \
  backend/src/anime_downloader/api/deps.py
git commit -m "$(cat <<'EOF'
Migrate existing library files to Jellyfin naming on startup.

Rename old slug-lang folders and merge duplicate VOSTFR/VF series rows.
EOF
)"
```

---

### Task 9: Spec/docs touch-up + final verification

**Files:**
- Modify: `docs/superpowers/specs/2026-11-18-anime-sama-adapter-design.md` — strike or note obsolete `series_title = {slug}-{lang}` and old path layout; point to 2026-11-19 spec
- Modify: `README.md` only if it documents `demo.local` or old paths

- [ ] **Step 1: Update obsolete design notes** (short “Superseded path naming” paragraph)

- [ ] **Step 2: Full verification**

Run:

```bash
cd backend && uv run pytest -v
rg -n "DemoAdapter|demo\\.local|demo_adapter" src || true
```

Expected: all tests PASS; no `DemoAdapter` in `src/`.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-11-18-anime-sama-adapter-design.md README.md
git commit -m "$(cat <<'EOF'
Document Jellyfin naming superseding slug-lang library paths.

Point the anime-sama adapter spec at the new library layout contract.
EOF
)"
```

---

## Self-review (plan vs spec)

| Spec requirement | Task |
|------------------|------|
| Jellyfin path layout | 1, 6 |
| `(Unknown)` year | 1 |
| `SeasonDiscovery` / `Series.release_year` | 2, 3 |
| Unique `(title, release_year)` | 3 |
| Anime-Sama oeuvre `#titreOeuvre` + year | 5 |
| Shared path builder all adapters | 1, 6 |
| Overwrite same path | 6 (same destination) |
| Migrate existing + merge vostfr/vf | 8 |
| Remove demo | 7 |
| Startup migration | 8 |
| Tests for path/adapter/worker/migration | 1, 5, 6, 7, 8 |

No TBD placeholders. Types consistent: `release_year: int | None` everywhere.
