import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.logging.logger import AppLogger


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.logger = AppLogger("http")

    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        start_time = time.time()

        client_ip = self._get_client_ip(request)

        self.logger.info(
            "Req started",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            client_ip=client_ip,
            user_agent=request.headers.get("user-agent")
        )

        try:
            response = await call_next(request)

            duration = round(time.time() - start_time, 4)

            self.logger.info(
                "Req completed",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration=duration
            )

            response.headers["X-Request-IP"] = request_id

            return response

        except Exception as e:
            duration = round(time.time() - start_time, 4)

            self.logger.error(
                "Req failed",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                duration=duration,
                error=str(e),
                error_type=type(e).__name__
            )
            raise

    def _get_client_ip(self, request: Request) -> str:
        forward_for = request.headers.get("x-forwarded-for")
        if forward_for:
            return forward_for.split(",")[0].strip()

        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip

        return request.client.host if request.client else "unknown"
