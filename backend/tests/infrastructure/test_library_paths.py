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