from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def _sqlite_url_for_path(db_path: str | Path) -> str:
    raw = str(db_path)
    if raw != ":memory:":
        Path(raw).expanduser().parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{raw}"


def create_engine_for_path(db_path: str | Path) -> Engine:
    return create_engine(
        _sqlite_url_for_path(db_path),
        connect_args={"check_same_thread": False},
    )


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


def _resolve_alembic_paths() -> tuple[Path | None, Path]:
    candidates = [
        Path(__file__).resolve().parents[4],
        Path.cwd(),
    ]
    for root in candidates:
        script_dir = root / "alembic"
        if script_dir.is_dir():
            ini_path = root / "alembic.ini"
            return (ini_path if ini_path.is_file() else None), script_dir
    raise FileNotFoundError("Could not locate Alembic migration directory 'alembic/'")


def run_migrations(db_path: str | Path) -> None:
    url = _sqlite_url_for_path(db_path)
    ini_path, script_dir = _resolve_alembic_paths()
    cfg = Config(str(ini_path)) if ini_path is not None else Config()
    cfg.attributes["configure_logger"] = False
    cfg.attributes["sqlalchemy_url_override"] = url
    cfg.set_main_option("script_location", str(script_dir))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
