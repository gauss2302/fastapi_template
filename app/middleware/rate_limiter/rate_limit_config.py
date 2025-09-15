from typing import Dict, Any, List
from fastapi import Request

from app.core.redis.redis import RedisService
from app.middleware.rate_limiter.rate_limiter import (
    RateLimiter,
    RateLimitType,
    user_based_identifier,
    ip_based_identifier,
    device_based_identifier,
    admin_bypass_condition,
    premium_user_condition
)


# ============================================================================
# PREDEFINED RATE LIMIT CONFIGURATIONS
# ============================================================================

class RateLimitPresets:
    """Predefined rate limit configurations using limits format."""

    # Authentication limits
    LOGIN = "5/minute;15/hour"
    REGISTRATION = "3/hour;10/day"
    PASSWORD_RESET = "3/30minutes;10/day"
    OAUTH_CALLBACK = "10/minute;50/hour"

    # API limits
    GENERAL_API = "100/minute;1000/hour"
    USER_PROFILE_UPDATE = "10/5minutes;50/hour"
    SEARCH_QUERY = "200/minute;2000/hour"

    # File operations
    FILE_UPLOAD = "5/5minutes;20/hour"
    BULK_OPERATION = "2/minute;10/hour"

    # Security sensitive
    ACCOUNT_DELETION = "1/day"
    SENSITIVE_DATA_ACCESS = "5/hour"
    ADMIN_ACTION = "50/minute;500/hour"

    # Public endpoints
    HEALTH_CHECK = "1000/minute"
    DOCUMENTATION = "100/minute"
    PUBLIC_SEARCH = "50/minute;500/hour"

    # Mobile specific
    MOBILE_LOGIN = "10/15minutes;50/day"
    MOBILE_REGISTRATION = "3/hour;5/day"
    MOBILE_TOKEN_REFRESH = "100/hour"


# ============================================================================
# CONFIGURATION HELPERS
# ============================================================================

def get_rate_limit_for_endpoint(endpoint_name: str) -> str:
    """Get rate limit configuration for a specific endpoint."""
    endpoint_limits = {
        # Auth endpoints
        "login": RateLimitPresets.LOGIN,
        "mobile_login": RateLimitPresets.MOBILE_LOGIN,
        "register": RateLimitPresets.REGISTRATION,
        "mobile_register": RateLimitPresets.MOBILE_REGISTRATION,
        "password_reset": RateLimitPresets.PASSWORD_RESET,
        "oauth_callback": RateLimitPresets.OAUTH_CALLBACK,

        # API endpoints
        "user_profile_update": RateLimitPresets.USER_PROFILE_UPDATE,
        "search": RateLimitPresets.SEARCH_QUERY,
        "file_upload": RateLimitPresets.FILE_UPLOAD,
        "bulk_operation": RateLimitPresets.BULK_OPERATION,

        # Security endpoints
        "account_deletion": RateLimitPresets.ACCOUNT_DELETION,
        "admin_action": RateLimitPresets.ADMIN_ACTION,
        "sensitive_data": RateLimitPresets.SENSITIVE_DATA_ACCESS,

        # Public endpoints
        "health": RateLimitPresets.HEALTH_CHECK,
        "docs": RateLimitPresets.DOCUMENTATION,
        "public_search": RateLimitPresets.PUBLIC_SEARCH,
    }

    return endpoint_limits.get(endpoint_name, RateLimitPresets.GENERAL_API)


def create_custom_rate_limit(
        calls_per_minute: int = None,
        calls_per_hour: int = None,
        calls_per_day: int = None,
        burst_calls: int = None,
        burst_period: str = "10seconds"
) -> str:
    """
    Create a custom rate limit string.

    Args:
        calls_per_minute: Number of calls allowed per minute
        calls_per_hour: Number of calls allowed per hour  
        calls_per_day: Number of calls allowed per day
        burst_calls: Number of burst calls allowed
        burst_period: Time period for burst (e.g., "10seconds", "1minute")

    Returns:
        Rate limit string in limits format

    Example:
        create_custom_rate_limit(calls_per_minute=10, calls_per_hour=100, burst_calls=5)
        # Returns: "5/10seconds;10/minute;100/hour"
    """
    limits = []

    # Add burst limit first (most restrictive)
    if burst_calls and burst_period:
        limits.append(f"{burst_calls}/{burst_period}")

    # Add time-based limits
    if calls_per_minute:
        limits.append(f"{calls_per_minute}/minute")
    if calls_per_hour:
        limits.append(f"{calls_per_hour}/hour")
    if calls_per_day:
        limits.append(f"{calls_per_day}/day")

    if not limits:
        # Default fallback
        limits.append("100/minute")

    return ";".join(limits)


# ============================================================================
# MONITORING AND MANAGEMENT
# ============================================================================

class RateLimitMonitor:
    """Monitor and manage rate limits."""

    def __init__(self, redis_service: RedisService):
        self.redis_service = redis_service
        self.rate_limiter = RateLimiter(redis_service)

    async def get_user_rate_limit_status(
            self,
            request: Request,
            limit_type: RateLimitType = RateLimitType.API
    ) -> Dict[str, Any]:
        """Get current rate limit status for a user."""
        key = self.rate_limiter._get_client_key(request)
        limit_str = self.rate_limiter.LIMITS.get(limit_type, "100/minute")

        # Parse first limit for status
        from limits import parse
        rate_limit = parse(limit_str.split(";")[0])

        # Get window stats
        window_stats = self.rate_limiter.limiter.get_window_stats(rate_limit, key)

        return {
            "limit": rate_limit.amount,
            "remaining": max(0, rate_limit.amount - window_stats.hit_count),
            "reset_time": window_stats.reset_time,
            "current_usage": window_stats.hit_count
        }

    async def reset_rate_limit_for_key(self, key: str) -> bool:
        """Reset rate limit for a specific key."""
        try:
            # Clear from storage
            await self.rate_limiter.storage.clear(key)
            return True
        except Exception:
            return False

    async def get_top_rate_limited_ips(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top rate-limited IP addresses."""
        # This would require custom implementation based on storage type
        # For now, return empty list
        return []

    async def block_ip_temporarily(self, ip: str, duration_minutes: int = 60) -> bool:
        """Temporarily block an IP address."""
        block_key = f"blocked_ip:{ip}"

        # Store block information
        await self.redis_service.set(
            block_key,
            {"blocked_at": "now", "duration": duration_minutes},
            expire=duration_minutes * 60
        )
        return True

    async def unblock_ip(self, ip: str) -> bool:
        """Remove IP from block list."""
        block_key = f"blocked_ip:{ip}"
        return await self.redis_service.delete(block_key)

    async def is_ip_blocked(self, ip: str) -> bool:
        """Check if IP is currently blocked."""
        block_key = f"blocked_ip:{ip}"
        return await self.redis_service.exists(block_key)


# ============================================================================
# ADVANCED CONFIGURATION PATTERNS
# ============================================================================

def create_tiered_rate_limit(
        basic_limit: str,
        premium_multiplier: float = 2.0,
        admin_multiplier: float = 10.0
) -> Dict[str, str]:
    """
    Create tiered rate limits for different user types.

    Args:
        basic_limit: Base rate limit string
        premium_multiplier: Multiplier for premium users
        admin_multiplier: Multiplier for admin users

    Returns:
        Dictionary with limits for each tier
    """
    from limits import parse

    # Parse the basic limit
    limits = [parse(limit) for limit in basic_limit.split(";")]

    # Create tiered limits
    tiers = {}

    # Basic tier
    tiers["basic"] = basic_limit

    # Premium tier
    premium_limits = []
    for limit in limits:
        new_amount = int(limit.amount * premium_multiplier)
        premium_limits.append(f"{new_amount}/{limit.per}")
    tiers["premium"] = ";".join(premium_limits)

    # Admin tier  
    admin_limits = []
    for limit in limits:
        new_amount = int(limit.amount * admin_multiplier)
        admin_limits.append(f"{new_amount}/{limit.per}")
    tiers["admin"] = ";".join(admin_limits)

    return tiers


def create_api_endpoint_limits() -> Dict[str, str]:
    """Create rate limits optimized for different API endpoints."""
    return {
        # High-frequency endpoints
        "health_check": "1000/minute",
        "metrics": "500/minute",
        "status": "200/minute",

        # Read operations
        "get_user": "200/minute;2000/hour",
        "list_items": "100/minute;1000/hour",
        "search": "50/minute;500/hour",

        # Write operations
        "create_item": "20/minute;200/hour",
        "update_item": "30/minute;300/hour",
        "delete_item": "10/minute;100/hour",

        # Expensive operations
        "bulk_import": "2/minute;10/hour",
        "generate_report": "5/minute;20/hour",
        "data_export": "3/minute;15/hour",

        # Authentication
        "login": "10/minute;50/hour",
        "logout": "20/minute",
        "refresh_token": "30/minute;200/hour",

        # Password operations
        "change_password": "5/minute;20/hour",
        "reset_password": "3/minute;10/hour",
        "forgot_password": "3/minute;5/hour",
    }


# ============================================================================
# USAGE EXAMPLES AND UTILITIES
# ============================================================================

def get_identifier_for_user_type(user_type: str):
    """Get appropriate identifier function for user type."""
    identifier_map = {
        "authenticated": user_based_identifier,
        "anonymous": ip_based_identifier,
        "mobile": device_based_identifier,
        "api": user_based_identifier,
    }
    return identifier_map.get(user_type, ip_based_identifier)


def get_skip_condition_for_user_type(user_type: str):
    """Get appropriate skip condition for user type."""
    skip_map = {
        "admin": admin_bypass_condition,
        "premium": premium_user_condition,
    }
    return skip_map.get(user_type)


# Export commonly used configurations
COMMON_LIMITS = {
    "auth": RateLimitPresets.LOGIN,
    "api": RateLimitPresets.GENERAL_API,
    "upload": RateLimitPresets.FILE_UPLOAD,
    "search": RateLimitPresets.SEARCH_QUERY,
    "admin": RateLimitPresets.ADMIN_ACTION,
}