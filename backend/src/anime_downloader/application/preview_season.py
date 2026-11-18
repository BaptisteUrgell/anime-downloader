from __future__ import annotations

from anime_downloader.domain.errors import DiscoveryFailed, DomainError
from anime_downloader.domain.model import SeasonDiscovery, SourceUrl
from anime_downloader.domain.ports import AdapterRegistry


def preview_season(url: str, registry: AdapterRegistry) -> SeasonDiscovery:
    source_url = SourceUrl.parse(url)
    adapter = registry.resolve(source_url)
    try:
        return adapter.discover_season(source_url)
    except DomainError:
        raise
    except Exception as exc:
        raise DiscoveryFailed(
            f"Season discovery failed for {source_url.value}: {exc}"
        ) from exc
