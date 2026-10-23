from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.analysis import router as analysis_router
from app.api.health import router as health_router
from app.schemas.errors import ErrorResponse

app = FastAPI(
    title="WindScope API",
    version="1.0.0",
)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    error = ErrorResponse(
        code=f"http_{exc.status_code}",
        message=str(exc.detail),
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=error.model_dump(exclude_none=True),
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    error = ErrorResponse(
        code="validation_error",
        message="Request validation failed.",
        details=exc.errors(),
    )
    return JSONResponse(
        status_code=422,
        content=jsonable_encoder(error.model_dump(exclude_none=True)),
    )


@app.get("/")
def root() -> dict[str, str]:
    return {"name": "WindScope API", "version": app.version}


app.include_router(health_router, prefix="/api/v1")
app.include_router(analysis_router, prefix="/api/v1")
