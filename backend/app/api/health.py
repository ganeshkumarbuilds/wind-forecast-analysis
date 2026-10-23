from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """Report that the API process is running, without asserting data availability."""
    return {"status": "ok"}
