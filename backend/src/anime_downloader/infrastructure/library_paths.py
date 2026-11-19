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