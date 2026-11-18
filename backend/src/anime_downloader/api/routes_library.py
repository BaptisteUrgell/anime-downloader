from typing import Annotated

from fastapi import APIRouter, Depends

from anime_downloader.api.deps import get_library_repository
from anime_downloader.api.schemas import LibrarySeriesResponse
from anime_downloader.application.list_library import list_library
from anime_downloader.domain.ports import LibraryRepository

router = APIRouter(prefix="/api/library", tags=["library"])


@router.get(
    "",
    response_model=list[LibrarySeriesResponse],
    operation_id="listLibrary",
)
def list_library_endpoint(
    library: Annotated[LibraryRepository, Depends(get_library_repository)],
) -> list[LibrarySeriesResponse]:
    return [
        LibrarySeriesResponse.model_validate(series)
        for series in list_library(library)
    ]
