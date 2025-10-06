import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_swagger_ui_html, get_swagger_ui_oauth2_redirect_html
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging.logger import config_structlog, AppLogger
from app.core.config.config import settings
from app.core.redis.redis import redis_service
from app.core.exceptions.exceptions import BaseAPIException
from app.api.v1.api import api_router
from app.middleware.auth_middleware.auth_middleware import AuthMiddleware
from app.middleware.rate_limiter.rate_limiter import RateLimitMiddleware
from app.middleware.rate_limiter.request_logging import RequestLoggingMiddleware

config_structlog()
logger = AppLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting application", app_name=settings.APP_NAME, version=settings.APP_VERSION)

    try:
        await redis_service.init_redis()
        logger.info("Redis connection established")

        yield

    except Exception as e:
        logger.error("Failed to start application", error=str(e))
        raise
    finally:
        logger.info("Shutting down application")
        await redis_service.close_redis()
        logger.info("Redis connection closed")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    openapi_url="/openapi.json",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)

app.state.redis_service = redis_service

app.add_middleware(RateLimitMiddleware, redis_service=redis_service)
app.add_middleware(RequestLoggingMiddleware)

# Security middleware
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.TRUSTED_HOSTS + (["*"] if settings.DEBUG else [])
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(AuthMiddleware)


@app.exception_handler(BaseAPIException)
async def api_exception_handler(request: Request, exc: BaseAPIException):
    """Handle custom API exceptions."""
    logger.error(
        "API exception occurred",
        error=exc.message,
        status_code=exc.status_code,
        details=exc.details,
        path=str(request.url),
        method=request.method,
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.message,
            "details": exc.details,
            "status_code": exc.status_code,
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions."""
    logger.warning(
        "HTTP exception occurred",
        status_code=exc.status_code,
        detail=exc.detail,
        path=str(request.url),
        method=request.method,
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors."""
    logger.warning(
        "Validation error occurred",
        errors=exc.errors(),
        path=str(request.url),
        method=request.method,
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation error",
            "details": exc.errors(),
            "status_code": status.HTTP_422_UNPROCESSABLE_ENTITY,
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions."""
    logger.error(
        "Unexpected error occurred",
        error=str(exc),
        error_type=type(exc).__name__,
        path=str(request.url),
        method=request.method,
        exc_info=True,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
        },
    )


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests."""
    start_time = time.time()

    logger.info(
        "Request started",
        method=request.method,
        url=str(request.url),
        client_host=request.client.host if request.client else None,
    )

    response = await call_next(request)

    process_time = time.time() - start_time

    logger.info(
        "Request completed",
        method=request.method,
        url=str(request.url),
        status_code=response.status_code,
        process_time=round(process_time, 4),
        client_host=request.client.host if request.client else None,
    )

    return response


# Include API router
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui():
    """Serve Swagger UI."""
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{settings.APP_NAME} - API Docs",
        oauth2_redirect_url="/docs/oauth2-redirect",
    )


@app.get("/docs/oauth2-redirect", include_in_schema=False)
async def swagger_ui_redirect():
    """Serve OAuth2 redirect page for Swagger."""
    return get_swagger_ui_oauth2_redirect_html()


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": f"Welcome to {settings.APP_NAME}",
        "version": settings.APP_VERSION,
        "docs": "/docs",
    }


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }
