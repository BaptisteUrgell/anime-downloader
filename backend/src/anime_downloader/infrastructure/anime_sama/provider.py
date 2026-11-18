from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx
import yt_dlp
from yt_dlp.utils import DownloadError

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

SEASON_PATH_RE = re.compile(r"^/catalogue/[^/]+/[^/]+/[^/]+/?$")

BDD_SCRIPT_RE = re.compile(
    r'<script[^>]*data-source=["\']bdd["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)
EPS_ARRAY_RE = re.compile(r"var\s+eps(\d+)\s*=\s*(\[.*?\])\s*;", re.DOTALL)
EPS_META_RE = re.compile(r"var\s+epsMeta\s*=\s*(\{.*?\})\s*;", re.DOTALL)
EPS_JETON_RE = re.compile(r'var\s+epsJeton\s*=\s*["\']([^"\']+)["\']\s*;')
LECTEURS_INFOS_RE = re.compile(r"var\s+lecteursInfos\s*=\s*(\{.*?\})\s*;", re.DOTALL)
SAISON_SUIVANTE_RE = re.compile(r"var\s+ctSaisonSuivante\s*=\s*([^;]+)\s*;")

_PERMANENT_DOWNLOAD_MARKERS = (
    "404",
    "410",
    "removed",
    "deleted",
    "not found",
    "video unavailable",
    "gone",
)


class AnimeSamaError(Exception):
    """Generic Anime-Sama extractor error."""


class PermanentMediaError(AnimeSamaError):
    """Host removed the video / 404: do not retry this player."""


class TokenExpiredError(AnimeSamaError):
    """epsJeton token expired and must be refreshed."""


@dataclass(frozen=True)
class SourceCandidate:
    player: int
    link_id: str
    host: str


@dataclass
class ProviderEpisode:
    index: int
    number: int
    season_url: str
    token: str
    sources: list[SourceCandidate]
    next_season_url: str | None = None
    title: str | None = None


@dataclass
class SeasonCache:
    season_url: str
    token: str
    episodes: list[ProviderEpisode]
    next_season_url: str | None


@dataclass(frozen=True)
class ProviderMedia:
    url: str
    headers: dict[str, str]
    resolution: str
    width: int | None
    height: int | None
    fps: float | None
    protocol: str | None
    player: int
    host: str


def _is_permanent_download_error(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in _PERMANENT_DOWNLOAD_MARKERS)


def _coerce_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _coerce_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _optional_json(raw: str) -> object | None:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _direct_stream_url(info: dict) -> str:
    url = info.get("url")
    if isinstance(url, str) and url.startswith("http"):
        return url
    requested = info.get("requested_formats")
    if isinstance(requested, list):
        for fmt in reversed(requested):
            if not isinstance(fmt, dict):
                continue
            candidate = fmt.get("url")
            if isinstance(candidate, str) and candidate.startswith("http"):
                return candidate
    return ""


class AnimeSamaProvider:
    def __init__(
        self,
        timeout: float = 15.0,
        max_retries_per_player: int = 3,
        retry_delay: float = 1.5,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self.max_retries_per_player = max_retries_per_player
        self.retry_delay = retry_delay
        self.user_agent = user_agent
        self.client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": user_agent,
                "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
            },
        )
        self._season_cache_lock = threading.Lock()
        self._season_cache: dict[str, SeasonCache] = {}

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> AnimeSamaProvider:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def get_cached_season(self, url: str) -> SeasonCache | None:
        with self._season_cache_lock:
            return self._season_cache.get(url)

    def matches(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False

        host = parsed.hostname.lower()
        is_valid_host = host == "anime-sama.to" or host.endswith(".anime-sama.to")
        return is_valid_host and bool(SEASON_PATH_RE.match(parsed.path))

    def discover_season(self, url: str) -> list[ProviderEpisode]:
        if not self.matches(url):
            raise ValueError(f"URL not supported by this provider: {url}")

        response = self.client.get(url)
        response.raise_for_status()
        html = response.text

        bdd_match = BDD_SCRIPT_RE.search(html)
        if not bdd_match:
            raise AnimeSamaError(
                "Missing <script data-source='bdd'> block on the page."
            )
        bdd_block = bdd_match.group(1)

        eps_arrays: dict[int, list[str]] = {}
        for match in EPS_ARRAY_RE.finditer(bdd_block):
            player_num = int(match.group(1))
            eps_arrays[player_num] = json.loads(match.group(2))

        if not eps_arrays:
            raise AnimeSamaError("No episode arrays (eps1..epsN) found.")

        meta_match = EPS_META_RE.search(bdd_block)
        eps_meta: dict[str, list[str]] = (
            json.loads(meta_match.group(1)) if meta_match else {}
        )

        jeton_match = EPS_JETON_RE.search(bdd_block)
        if not jeton_match:
            raise AnimeSamaError("epsJeton token not found on the page.")
        token = jeton_match.group(1)

        infos_match = LECTEURS_INFOS_RE.search(html)
        lecteurs_infos: dict[str, dict[str, object]] = {}
        if infos_match:
            parsed_infos = _optional_json(infos_match.group(1))
            if isinstance(parsed_infos, dict):
                lecteurs_infos = {
                    str(key): value
                    for key, value in parsed_infos.items()
                    if isinstance(value, dict)
                }

        next_season_url: str | None = None
        next_match = SAISON_SUIVANTE_RE.search(html)
        if next_match:
            raw_next = _optional_json(next_match.group(1).strip())
            if isinstance(raw_next, str) and raw_next:
                next_season_url = urljoin(url, raw_next)

        episode_count = max(len(arr) for arr in eps_arrays.values())
        sorted_players = sorted(eps_arrays.keys())
        episodes: list[ProviderEpisode] = []

        for idx in range(episode_count):
            sources: list[SourceCandidate] = []
            for player_num in sorted_players:
                arr = eps_arrays[player_num]
                raw_entry = arr[idx] if idx < len(arr) else ""
                if not raw_entry or not raw_entry.startswith("lien:"):
                    continue

                link_id = raw_entry.split(":", 1)[1]
                host = eps_meta.get(link_id, [""])[0]

                if host and lecteurs_infos.get(host, {}).get("mort") is True:
                    continue

                sources.append(
                    SourceCandidate(
                        player=player_num,
                        link_id=link_id,
                        host=host,
                    )
                )

            episodes.append(
                ProviderEpisode(
                    index=idx,
                    number=idx + 1,
                    season_url=url,
                    token=token,
                    sources=sources,
                    next_season_url=next_season_url,
                )
            )

        cached = SeasonCache(
            season_url=url,
            token=token,
            episodes=episodes,
            next_season_url=next_season_url,
        )
        with self._season_cache_lock:
            self._season_cache[url] = cached
        return episodes

    def _resolve_embed_url(self, link_id: str, token: str, season_url: str) -> str:
        endpoint = urljoin(season_url, "/api/lien.php")
        resp = self.client.get(
            endpoint,
            params={"j": token, "l": link_id},
            headers={
                "Referer": season_url,
                "Accept": "application/json, text/plain, */*",
            },
        )
        if resp.status_code in {401, 403}:
            raise TokenExpiredError(f"Token rejected or expired (HTTP {resp.status_code})")
        if resp.status_code in {404, 410}:
            raise PermanentMediaError(
                f"Link {link_id} not found (HTTP {resp.status_code})"
            )
        resp.raise_for_status()
        payload = resp.json()
        if isinstance(payload, str):
            embed_url = payload.strip()
        elif isinstance(payload, dict):
            embed_url = next(
                (
                    v.strip()
                    for v in payload.values()
                    if isinstance(v, str) and v.startswith("http")
                ),
                "",
            )
        else:
            embed_url = ""
        if not embed_url.startswith("http"):
            raise AnimeSamaError(
                f"Unexpected response for lien:{link_id} -> {payload!r}"
            )
        return embed_url

    def _cached_episode(self, season_url: str, number: int) -> ProviderEpisode:
        season = self.get_cached_season(season_url)
        if season is None:
            self.discover_season(season_url)
            season = self.get_cached_season(season_url)
        if season is None:
            raise AnimeSamaError(f"Season not found after discovery: {season_url}")
        for episode in season.episodes:
            if episode.number == number:
                return episode
        raise AnimeSamaError(f"Episode {number} not found for {season_url}.")

    def _extract_best_stream(self, embed_url: str) -> dict:
        options = {
            # Prefer progressive mp4/http over HLS manifests when possible.
            "format": (
                "best[ext=mp4][protocol^=http][protocol!*=m3u8]/"
                "best[protocol^=http][protocol!*=m3u8]/"
                "best"
            ),
            "format_sort": ["res", "fps", "tbr"],
            "format_sort_force": True,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "skip_download": True,
            "http_headers": {
                "User-Agent": self.user_agent,
                "Referer": embed_url,
            },
        }
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(embed_url, download=False)
        except DownloadError as exc:
            if _is_permanent_download_error(str(exc)):
                raise PermanentMediaError(str(exc)) from exc
            raise
        if not isinstance(info, dict):
            raise AnimeSamaError(f"No stream extracted for {embed_url}")
        return info

    def _media_from_stream(
        self,
        info: dict,
        embed_url: str,
        source: SourceCandidate,
    ) -> ProviderMedia:
        stream_url = _direct_stream_url(info)
        if not stream_url:
            raise AnimeSamaError(f"Stream has no direct URL for {embed_url}")

        width = _coerce_int(info.get("width"))
        height = _coerce_int(info.get("height"))
        if width is not None and height is not None:
            resolution = f"{width}x{height}"
        else:
            resolution = ""
        protocol = info.get("protocol")
        headers = {
            "User-Agent": self.user_agent,
            "Referer": embed_url,
        }
        raw_headers = info.get("http_headers") or {}
        if isinstance(raw_headers, dict):
            for key, value in raw_headers.items():
                headers[str(key)] = str(value)
        headers["Referer"] = embed_url
        return ProviderMedia(
            url=stream_url,
            headers=headers,
            resolution=resolution,
            width=width,
            height=height,
            fps=_coerce_float(info.get("fps")),
            protocol=protocol if isinstance(protocol, str) else None,
            player=source.player,
            host=source.host,
        )

    def resolve_media_for_episode(self, season_url: str, number: int) -> ProviderMedia:
        episode = self._cached_episode(season_url, number)
        if not episode.sources:
            raise AnimeSamaError(f"No players available for episode {number}.")

        players = [source.player for source in episode.sources]
        token_refreshed = False
        failures: list[str] = []

        for player in players:
            attempt = 0
            while attempt < self.max_retries_per_player:
                attempt += 1
                episode = self._cached_episode(season_url, number)
                source = next(
                    (item for item in episode.sources if item.player == player),
                    None,
                )
                if source is None:
                    failures.append(f"player {player} missing after refresh")
                    break
                try:
                    embed_url = self._resolve_embed_url(
                        source.link_id,
                        episode.token,
                        season_url,
                    )
                    info = self._extract_best_stream(embed_url)
                    return self._media_from_stream(info, embed_url, source)
                except TokenExpiredError as exc:
                    if not token_refreshed:
                        self.discover_season(season_url)
                        token_refreshed = True
                        attempt -= 1
                        continue
                    failures.append(f"player {player}: {exc}")
                    if attempt < self.max_retries_per_player:
                        time.sleep(self.retry_delay * attempt)
                except PermanentMediaError as exc:
                    failures.append(f"player {player}: {exc}")
                    break
                except Exception as exc:
                    failures.append(f"player {player}: {exc}")
                    if attempt < self.max_retries_per_player:
                        time.sleep(self.retry_delay * attempt)

        detail = "; ".join(failures) if failures else "erreur inconnue"
        raise AnimeSamaError(
            f"All players failed for episode {number}: {detail}"
        )