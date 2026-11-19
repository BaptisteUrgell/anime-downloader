from __future__ import annotations

import ast
import json
from pathlib import Path
import threading
import time

from fastapi.testclient import TestClient
import pytest

from anime_downloader.api.main import app as exported_app, create_app
from anime_downloader.application.start_season_download import start_season_download
from anime_downloader.domain.model import (
    DownloadJob,
    Episode,
    EpisodeStatus,
    JobStatus,
    MediaLocator,
)
from anime_downloader.infrastructure.adapter_registry import AdapterRegistry
from anime_downloader.infrastructure.db.session import (
    create_engine_for_path,
    make_session_factory,
    run_migrations,
)
from tests.support.fake_season_adapter import FakeSeasonAdapter
from anime_downloader.infrastructure.http_downloader import FakeMediaDownloader
from anime_downloader.infrastructure.ids import UuidIdGenerator
from anime_downloader.infrastructure.persistence.job_repository import (
    SqlAlchemyJobRepository,
)
from anime_downloader.infrastructure.persistence.library_repository import (
    SqlAlchemyLibraryRepository,
)


def _app_with_fake_season(data_dir: str | Path | None = None, **kwargs):
    kwargs.setdefault("registry", AdapterRegistry([FakeSeasonAdapter()]))
    kwargs.setdefault("downloader", FakeMediaDownloader())
    return create_app(data_dir, **kwargs)


def _poll_until(predicate, timeout: float = 5.0, interval: float = 0.02):
    deadline = time.monotonic() + timeout
    last_value = None
    while time.monotonic() < deadline:
        last_value = predicate()
        if last_value:
            return last_value
        time.sleep(interval)
    raise AssertionError(f"Condition not met within {timeout}s; last={last_value!r}")


def test_preview_season_returns_fake_episode_count_and_metadata(tmp_path: Path) -> None:
    app = _app_with_fake_season(tmp_path)
    with TestClient(app) as client:
        resp = client.post(
            "/api/jobs/preview",
            json={"url": "https://fake.local/season/demo-show/1"},
        )

    assert resp.status_code == 200
    assert resp.json() == {
        "series_title": "demo-show",
        "season_number": 1,
        "episode_count": 3,
        "episodes": [
            {"number": 1, "title": None},
            {"number": 2, "title": None},
            {"number": 3, "title": None},
        ],
    }


def test_preview_season_maps_domain_errors_to_http_statuses(tmp_path: Path) -> None:
    app = _app_with_fake_season(tmp_path)
    with TestClient(app) as client:
        invalid_resp = client.post("/api/jobs/preview", json={"url": "not-a-url"})
        unknown_resp = client.post(
            "/api/jobs/preview",
            json={"url": "https://unknown.example/season/show/1"},
        )
        broken_resp = client.post(
            "/api/jobs/preview",
            json={"url": "https://fake.local/season/missing-season-number"},
        )

    assert invalid_resp.status_code == 400
    assert "detail" in invalid_resp.json()
    assert unknown_resp.status_code == 400
    assert "detail" in unknown_resp.json()
    assert broken_resp.status_code == 502
    assert "detail" in broken_resp.json()


def test_create_job_returns_pending_or_running_and_completes_library(
    tmp_path: Path,
) -> None:
    release_download = threading.Event()

    class GatedDownloader:
        def download(self, media: MediaLocator, destination: str, *, on_progress=None) -> str:
            release_download.wait(timeout=5.0)
            return FakeMediaDownloader(payload=b"video-data").download(
                media, destination
            )

    app = _app_with_fake_season(tmp_path, downloader=GatedDownloader())
    with TestClient(app) as client:
        empty_jobs = client.get("/api/jobs")
        assert empty_jobs.status_code == 200
        assert empty_jobs.json() == []

        empty_lib = client.get("/api/library")
        assert empty_lib.status_code == 200
        assert empty_lib.json() == []

        create_resp = client.post(
            "/api/jobs",
            json={"url": "https://fake.local/season/demo-show/1"},
        )
        assert create_resp.status_code in {200, 201}
        created_job = create_resp.json()
        job_id = created_job["id"]
        assert created_job["status"] in {"pending", "running"}
        assert created_job["total_episodes"] == 3
        assert created_job["adapter_id"] == "fake"
        assert created_job["season_id"] is not None

        release_download.set()

        def _job_completed():
            res = client.get(f"/api/jobs/{job_id}")
            assert res.status_code == 200
            body = res.json()
            return body if body["status"] == "completed" else None

        completed_job = _poll_until(_job_completed)
        assert completed_job["completed_episodes"] == 3
        assert completed_job["failed_episodes"] == 0

        jobs_resp = client.get("/api/jobs")
        assert jobs_resp.status_code == 200
        assert [j["id"] for j in jobs_resp.json()] == [job_id]

        missing_resp = client.get("/api/jobs/non-existent-id")
        assert missing_resp.status_code == 404

        lib_resp = client.get("/api/library")
        assert lib_resp.status_code == 200
        lib_data = lib_resp.json()
        assert len(lib_data) == 1
        assert lib_data[0]["title"] == "demo-show"
        assert len(lib_data[0]["seasons"]) == 1
        season_node = lib_data[0]["seasons"][0]
        assert season_node["number"] == 1
        assert len(season_node["episodes"]) == 3
        for idx, ep in enumerate(season_node["episodes"], start=1):
            assert ep["number"] == idx
            assert ep["status"] == "completed"
            assert ep["file_path"] is not None
            assert Path(ep["file_path"]).is_file()


def test_create_app_downloads_fake_season_into_jellyfin_path(
    tmp_path: Path,
) -> None:
    app = _app_with_fake_season(tmp_path)
    with TestClient(app) as client:
        resp = client.post(
            "/api/jobs",
            json={"url": "https://fake.local/season/solo-demo/1"},
        )
        assert resp.status_code in {200, 201}
        job_id = resp.json()["id"]

        def _done():
            r = client.get(f"/api/jobs/{job_id}")
            body = r.json()
            return body if body["status"] == "completed" else None

        done_job = _poll_until(_done)
        assert done_job["completed_episodes"] == 3

    expected_ep1 = (
        tmp_path
        / "library"
        / "solo-demo (2020)"
        / "Season 01"
        / "solo-demo S01E01.mp4"
    )
    assert expected_ep1.is_file()


def test_retry_failed_endpoint_enqueues_job_and_recovers_failed_episodes(
    tmp_path: Path,
) -> None:
    fail_ep2 = True

    class ToggleDownloader:
        def download(self, media: MediaLocator, destination: str, *, on_progress=None) -> str:
            if fail_ep2 and media.url.endswith("/2.mp4"):
                raise ConnectionError("cdn 503")
            return FakeMediaDownloader().download(media, destination)

    app = _app_with_fake_season(
        tmp_path,
        downloader=ToggleDownloader(),
        worker_sleep=lambda _: None,
    )
    with TestClient(app) as client:
        unknown_season = client.post(
            "/api/jobs/retry-failed",
            json={"season_id": "missing-season"},
        )
        assert unknown_season.status_code == 404

        start_resp = client.post(
            "/api/jobs",
            json={"url": "https://fake.local/season/retry-api/1"},
        )
        assert start_resp.status_code in {200, 201}
        initial_job = start_resp.json()
        initial_job_id = initial_job["id"]
        season_id = initial_job["season_id"]

        def _initial_finished():
            body = client.get(f"/api/jobs/{initial_job_id}").json()
            return body if body["status"] in {"completed", "failed"} else None

        finished_initial = _poll_until(_initial_finished)
        assert finished_initial["completed_episodes"] == 2
        assert finished_initial["failed_episodes"] == 1

        fail_ep2 = False
        retry_resp = client.post(
            "/api/jobs/retry-failed",
            json={"season_id": season_id},
        )
        assert retry_resp.status_code in {200, 201}
        retry_job = retry_resp.json()
        retry_job_id = retry_job["id"]
        assert retry_job_id != initial_job_id
        assert retry_job["status"] in {"pending", "running", "completed"}

        def _retry_completed():
            body = client.get(f"/api/jobs/{retry_job_id}").json()
            return body if body["status"] == "completed" else None

        completed_retry = _poll_until(_retry_completed)
        assert completed_retry["completed_episodes"] == 3
        assert completed_retry["failed_episodes"] == 0

        no_failed_left = client.post(
            "/api/jobs/retry-failed",
            json={"season_id": season_id},
        )
        assert no_failed_left.status_code == 409


def test_lifespan_resumes_incomplete_jobs_and_stops_worker_on_shutdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "app.db"
    library_root = tmp_path / "library"
    run_migrations(db_path)
    engine = create_engine_for_path(db_path)
    session_factory = make_session_factory(engine)
    jobs = SqlAlchemyJobRepository(session_factory)
    library = SqlAlchemyLibraryRepository(session_factory)
    registry = AdapterRegistry([FakeSeasonAdapter(episode_count=3)])
    ids = UuidIdGenerator()

    crashed_job = start_season_download(
        url="https://fake.local/season/resume-show/1",
        registry=registry,
        jobs=jobs,
        library=library,
        ids=ids,
    )
    assert crashed_job.season_id is not None
    eps = library.list_episodes(crashed_job.season_id)

    ep1_path = (library_root / "resume-show" / "1" / "S01E01 - Episode 1.mp4").resolve()
    ep1_path.parent.mkdir(parents=True, exist_ok=True)
    ep1_path.write_bytes(b"kept-from-before-crash")

    library.upsert_episode(
        Episode(
            id=eps[0].id,
            season_id=crashed_job.season_id,
            number=1,
            title=eps[0].title,
            status=EpisodeStatus.COMPLETED,
            source_url=eps[0].source_url,
            file_path=str(ep1_path),
        )
    )
    library.upsert_episode(
        Episode(
            id=eps[1].id,
            season_id=crashed_job.season_id,
            number=2,
            title=eps[1].title,
            status=EpisodeStatus.DOWNLOADING,
            source_url=eps[1].source_url,
        )
    )
    jobs.save(
        DownloadJob(
            id=crashed_job.id,
            source_url=crashed_job.source_url,
            adapter_id=crashed_job.adapter_id,
            status=JobStatus.RUNNING,
            series_id=crashed_job.series_id,
            season_id=crashed_job.season_id,
            total_episodes=3,
            completed_episodes=1,
            failed_episodes=0,
        )
    )
    engine.dispose()

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = _app_with_fake_season(
        registry=AdapterRegistry([FakeSeasonAdapter(episode_count=3)]),
    )
    with TestClient(app) as client:
        def _resumed_done():
            body = client.get(f"/api/jobs/{crashed_job.id}").json()
            return body if body["status"] == "completed" else None

        resumed = _poll_until(_resumed_done)
        assert resumed["completed_episodes"] == 3
        worker = app.state.container.worker
        assert worker._thread is not None and worker._thread.is_alive()

    assert not worker._thread.is_alive()
    assert ep1_path.read_bytes() == b"kept-from-before-crash"
    assert exported_app is not None


def test_dismiss_job_and_dismiss_completed(tmp_path: Path) -> None:
    app = _app_with_fake_season(tmp_path)
    with TestClient(app) as client:
        created = client.post(
            "/api/jobs",
            json={"url": "https://fake.local/season/demo-show/1"},
        )
        assert created.status_code == 201
        job_id = created.json()["id"]

        _poll_until(
            lambda: client.get(f"/api/jobs/{job_id}").json()["status"]
            in {"completed", "failed"}
        )

        listed_before = client.get("/api/jobs")
        assert listed_before.status_code == 200
        assert any(j["id"] == job_id for j in listed_before.json())

        dismissed = client.post(f"/api/jobs/{job_id}/dismiss")
        assert dismissed.status_code == 200
        assert dismissed.json()["dismissed_at"] is not None

        listed_after = client.get("/api/jobs")
        assert all(j["id"] != job_id for j in listed_after.json())


def test_dismiss_active_job_conflict(tmp_path: Path) -> None:
    release = threading.Event()

    class GatedDownloader:
        def download(self, media, destination, *, on_progress=None) -> str:
            release.wait(timeout=5.0)
            return FakeMediaDownloader(payload=b"x").download(media, destination)

    app = _app_with_fake_season(tmp_path, downloader=GatedDownloader())
    with TestClient(app) as client:
        created = client.post(
            "/api/jobs",
            json={"url": "https://fake.local/season/demo-show/1"},
        )
        job_id = created.json()["id"]
        _poll_until(
            lambda: client.get(f"/api/jobs/{job_id}").json()["status"] == "running"
        )
        resp = client.post(f"/api/jobs/{job_id}/dismiss")
        assert resp.status_code == 409
        release.set()


def test_dismiss_completed_endpoint_counts(tmp_path: Path) -> None:
    app = _app_with_fake_season(tmp_path)
    with TestClient(app) as client:
        created = client.post(
            "/api/jobs",
            json={"url": "https://fake.local/season/demo-show/1"},
        )
        job_id = created.json()["id"]
        _poll_until(
            lambda: client.get(f"/api/jobs/{job_id}").json()["status"] == "completed"
        )
        resp = client.post("/api/jobs/dismiss-completed")
        assert resp.status_code == 200
        assert resp.json() == {"dismissed_count": 1}
        assert client.get("/api/jobs").json() == []


def test_cors_allows_frontend_origin(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    with TestClient(app) as client:
        preflight = client.options(
            "/api/jobs",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert preflight.status_code == 200
    assert "access-control-allow-origin" in preflight.headers


def test_api_layer_top_level_imports_and_pydantic_boundary() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    api_dir = backend_root / "src" / "anime_downloader" / "api"
    domain_dir = backend_root / "src" / "anime_downloader" / "domain"

    for py_file in sorted(api_dir.glob("*.py")) + [Path(__file__).resolve()]:
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        top_level_imports = {
            node
            for node in tree.body
            if isinstance(node, (ast.Import, ast.ImportFrom))
        }
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                assert node in top_level_imports, (
                    f"Inline import found in {py_file.name}"
                )

    for py_file in sorted(domain_dir.glob("*.py")):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith(("pydantic", "fastapi"))
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith(("pydantic", "fastapi"))


def test_exported_openapi_json_matches_app_schema() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    openapi_file = repo_root / "frontend" / "openapi.json"
    assert openapi_file.is_file()

    exported_spec = json.loads(openapi_file.read_text(encoding="utf-8"))
    live_spec = create_app("/tmp/ad-data").openapi()
    assert exported_spec == live_spec
    assert set(exported_spec["paths"].keys()) == {
        "/api/jobs/preview",
        "/api/jobs",
        "/api/jobs/retry-failed",
        "/api/jobs/dismiss-completed",
        "/api/jobs/{id}",
        "/api/jobs/{id}/dismiss",
        "/api/library",
    }

