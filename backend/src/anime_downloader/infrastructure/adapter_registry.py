from __future__ import annotations

from anime_downloader.domain.errors import NoAdapterFound
from anime_downloader.domain.model import SourceUrl
from anime_downloader.domain.ports import SourceAdapter


class AdapterRegistry:
    def __init__(self, adapters: list[SourceAdapter]) -> None:
        self._adapters = list(adapters)

    def resolve(self, url: SourceUrl) -> SourceAdapter:
        for adapter in self._adapters:
            if adapter.matches(url):
                return adapter
        raise NoAdapterFound(f"No adapter found for URL: {url.value}")