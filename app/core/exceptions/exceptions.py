from typing import Any, Dict, Optional


class BaseAPIException(Exception):
    """Base exception for API errors."""
    def __init__(self, message: str, status_code: int = 500, details: Optional[Dict[str, Any]] = None) -> None:
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class ValidationError(BaseAPIException):
    """Validation error exception."""
    def __init__(self, message: str = "Validation error", details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, status_code=422, details=details)


class AuthenticationError(BaseAPIException):
    """Authentication error exception."""

    def __init__(
            self,
            message: str = "Authentication failed",
            details: Optional[Dict[str, Any]] = None
    ) -> None:
        super().__init__(message, status_code=401, details=details)


class AuthorizationError(BaseAPIException):
    """Authorization error exception."""

    def __init__(
            self,
            message: str = "Insufficient permissions",
            details: Optional[Dict[str, Any]] = None
    ) -> None:
        super().__init__(message, status_code=403, details=details)


class NotFoundError(BaseAPIException):
    """Not found error exception."""

    def __init__(
            self,
            message: str = "Resource not found",
            details: Optional[Dict[str, Any]] = None
    ) -> None:
        super().__init__(message, status_code=404, details=details)


class ConflictError(BaseAPIException):
    """Conflict error exception."""

    def __init__(
            self,
            message: str = "Resource conflict",
            details: Optional[Dict[str, Any]] = None
    ) -> None:
        super().__init__(message, status_code=409, details=details)


class RateLimitError(BaseAPIException):
    """Rate limit error exception."""

    def __init__(
            self,
            message: str = "Rate limit exceeded",
            details: Optional[Dict[str, Any]] = None
    ) -> None:
        super().__init__(message, status_code=429, details=details)