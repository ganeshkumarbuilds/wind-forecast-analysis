from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException

from app.schemas.analysis import AnalysisRequest, AnalysisResponse
from app.services.analysis import UpstreamDataValidationError, run_analysis
from app.services.elexon_client import (
    ElexonClient,
    ElexonConnectionError,
    ElexonHTTPError,
    ElexonResponseError,
    ElexonTimeoutError,
)

router = APIRouter()


def get_elexon_client() -> Iterator[ElexonClient]:
    with ElexonClient() as client:
        yield client


@router.post(
    "/analysis",
    response_model=AnalysisResponse,
    summary="Analyze January 2026 wind forecast availability",
)
def analyze(
    request: AnalysisRequest,
    client: ElexonClient = Depends(get_elexon_client),
) -> AnalysisResponse:
    try:
        return run_analysis(request, client=client)
    except ElexonTimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail="The Elexon API request timed out.",
        ) from exc
    except (
        ElexonConnectionError,
        ElexonHTTPError,
        ElexonResponseError,
    ) as exc:
        raise HTTPException(
            status_code=502,
            detail="The Elexon API request failed or returned invalid data.",
        ) from exc
    except UpstreamDataValidationError as exc:
        raise HTTPException(
            status_code=502,
            detail="The Elexon API returned data that could not be processed.",
        ) from exc
