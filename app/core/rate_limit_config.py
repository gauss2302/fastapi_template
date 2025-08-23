from fastapi import Request
from app.middleware.rate_limiter import RateLimitType, RateLimitConfig
import hashlib
from typing import Optional


# ============================================================================
# CUSTOM KEY FUNCTIONS (separate from config classes)
# ============================================================================

def user_based_key(request: Request) -> str:
    """Generate rate limit key based on authenticated user."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        # Hash token for user identification
        return f"user:{hashlib.md5(token.encode()).hexdigest()[:16]}"

    # Fallback to IP for unauthenticated users
    return f"ip:{request.client.host if request.client else 'unknown'}"


def ip_and_endpoint_key(request: Request) -> str:
    """Generate key based on IP and specific endpoint."""
    ip = request.client.host if request.client else "unknown"
    endpoint = request.url.path.replace("/", "_")
    return f"ip_endpoint:{ip}:{endpoint}"


def strict_ip_key(request: Request) -> str:
    """Strict IP-based key for sensitive operations."""
    # Check for real IP behind proxy
    real_ip = (
            request.headers.get("x-forwarded-for", "").split(",")[0].strip() or
            request.headers.get("x-real-ip") or
            (request.client.host if request.client else "unknown")
    )
    return f"strict_ip:{real_ip}"


def mobile_device_key(request: Request) -> str:
    """Generate rate limit key based on mobile device ID or IP."""
    device_id = request.headers.get("X-Device-ID")
    user_agent = request.headers.get("User-Agent", "")

    if device_id:
        return f"mobile_device:{device_id}"

    # Fallback: Use combination of IP and User-Agent hash for device identification
    ip = request.client.host if request.client else "unknown"
    ua_hash = hashlib.md5(user_agent.encode()).hexdigest()[:12]
    return f"mobile_fallback:{ip}:{ua_hash}"


def default_ip_key(request: Request) -> str:
    """Default IP-based key."""
    return f"ip:{request.client.host if request.client else 'unknown'}"


# ============================================================================
# HELPER FUNCTIONS FOR SKIP CONDITIONS
# ============================================================================

def admin_bypass_check(request: Request) -> bool:
    """Check for admin bypass header."""
    return request.headers.get("x-admin-bypass") == "secret_key"


def premium_user_check(request: Request) -> bool:
    """Check for premium user header."""
    return request.headers.get("x-premium-user") == "true"


# ============================================================================
# RATE LIMIT CONFIGURATION FACTORY
# ============================================================================

class RateLimitConfigFactory:
    """Factory class to create rate limit configurations without serialization issues."""

    @staticmethod
    def create_config(
            calls: int,
            period: int,
            burst: Optional[int] = None,
            key_func_name: str = "default_ip",
            skip_condition: Optional[str] = None
    ) -> RateLimitConfig:
        """Create a rate limit configuration with proper function references."""

        # Map function names to actual functions
        key_func_map = {
            "default_ip": default_ip_key,
            "user_based": user_based_key,
            "strict_ip": strict_ip_key,
            "mobile_device": mobile_device_key,
            "ip_and_endpoint": ip_and_endpoint_key,
        }

        skip_func_map = {
            "admin_bypass": admin_bypass_check,
            "premium_user": premium_user_check,
        }

        key_func = key_func_map.get(key_func_name, default_ip_key)
        skip_func = skip_func_map.get(skip_condition) if skip_condition else None

        return RateLimitConfig(
            calls=calls,
            period=period,
            burst=burst,
            key_func=key_func,
            skip_if=skip_func
        )


# ============================================================================
# PREDEFINED CONFIGURATIONS USING FACTORY
# ============================================================================

# Authentication-related configurations
AUTH_CONFIGS = {
    "login": RateLimitConfigFactory.create_config(
        calls=5,
        period=300,  # 5 attempts per 5 minutes
        burst=2,
        key_func_name="strict_ip"
    ),

    "registration": RateLimitConfigFactory.create_config(
        calls=3,
        period=3600,  # 3 registrations per hour
        key_func_name="strict_ip"
    ),

    "password_reset": RateLimitConfigFactory.create_config(
        calls=3,
        period=1800,  # 3 password resets per 30 minutes
        key_func_name="user_based"
    ),

    "oauth_callback": RateLimitConfigFactory.create_config(
        calls=10,
        period=60,  # 10 OAuth callbacks per minute
        key_func_name="strict_ip"
    ),
}

# Mobile-specific configurations
MOBILE_CONFIGS = {
    "mobile_registration": RateLimitConfigFactory.create_config(
        calls=3,
        period=3600,  # 3 registrations per hour per device
        key_func_name="mobile_device"
    ),

    "mobile_login": RateLimitConfigFactory.create_config(
        calls=10,
        period=900,  # 10 login attempts per 15 minutes per device
        burst=3,
        key_func_name="mobile_device"
    ),

    "mobile_token_refresh": RateLimitConfigFactory.create_config(
        calls=50,
        period=3600,  # 50 refreshes per hour per device
        key_func_name="mobile_device"
    ),

    "mobile_oauth": RateLimitConfigFactory.create_config(
        calls=5,
        period=600,  # 5 OAuth attempts per 10 minutes per device
        key_func_name="mobile_device"
    ),
}

# API operation configurations
API_CONFIGS = {
    "user_profile_update": RateLimitConfigFactory.create_config(
        calls=10,
        period=300,  # 10 updates per 5 minutes
        key_func_name="user_based"
    ),

    "file_upload": RateLimitConfigFactory.create_config(
        calls=5,
        period=300,  # 5 uploads per 5 minutes
        burst=2,
        key_func_name="user_based"
    ),

    "search_query": RateLimitConfigFactory.create_config(
        calls=100,
        period=60,  # 100 searches per minute
        key_func_name="user_based"
    ),

    "admin_action": RateLimitConfigFactory.create_config(
        calls=20,
        period=60,  # 20 admin actions per minute
        key_func_name="user_based",
        skip_condition="admin_bypass"
    ),
}

# Security-sensitive configurations
SECURITY_CONFIGS = {
    "account_deletion": RateLimitConfigFactory.create_config(
        calls=1,
        period=86400,  # 1 account deletion per day
        key_func_name="user_based"
    ),

    "sensitive_data_access": RateLimitConfigFactory.create_config(
        calls=5,
        period=3600,  # 5 accesses per hour
        key_func_name="user_based"
    ),

    "admin_login": RateLimitConfigFactory.create_config(
        calls=3,
        period=1800,  # 3 admin login attempts per 30 minutes
        key_func_name="strict_ip"
    ),
}

# Public API configurations
PUBLIC_CONFIGS = {
    "health_check": RateLimitConfigFactory.create_config(
        calls=1000,
        period=60,  # 1000 health checks per minute
        key_func_name="default_ip"
    ),

    "documentation": RateLimitConfigFactory.create_config(
        calls=100,
        period=60,  # 100 doc requests per minute
        key_func_name="strict_ip"
    ),
}

# Merge mobile configs into auth configs
AUTH_CONFIGS.update(MOBILE_CONFIGS)


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def get_rate_limit_config(config_name: str, category: str = "auth") -> RateLimitConfig:
    """
    Get a predefined rate limit configuration.

    Args:
        config_name: Name of the configuration
        category: Category (auth, api, security, public)

    Returns:
        RateLimitConfig object

    Example:
        config = get_rate_limit_config("login", "auth")
    """
    categories = {
        "auth": AUTH_CONFIGS,
        "api": API_CONFIGS,
        "security": SECURITY_CONFIGS,
        "public": PUBLIC_CONFIGS,
    }

    category_configs = categories.get(category, {})
    if config_name not in category_configs:
        raise ValueError(f"Configuration '{config_name}' not found in category '{category}'")

    return category_configs[config_name]


# ============================================================================
# MONITORING HELPERS
# ============================================================================

class RateLimitMonitor:
    """Helper class for monitoring rate limit usage."""

    @staticmethod
    async def get_current_usage(redis_service, key: str) -> dict:
        """Get current usage for a rate limit key."""
        count = await redis_service.get(key)
        ttl = await redis_service.redis.ttl(key) if redis_service.redis else 0

        return {
            "current_count": int(count) if count else 0,
            "ttl_seconds": ttl,
            "key": key
        }

    @staticmethod
    async def reset_rate_limit(redis_service, key: str) -> bool:
        """Reset rate limit for a specific key."""
        return await redis_service.delete(key)

    @staticmethod
    async def get_all_rate_limits(redis_service, pattern: str = "rate_limit:*") -> list:
        """Get all current rate limit keys and their usage."""
        if not redis_service.redis:
            return []

        try:
            keys = await redis_service.redis.keys(pattern)
            results = []

            for key in keys:
                usage = await RateLimitMonitor.get_current_usage(redis_service, key)
                results.append(usage)

            return results
        except Exception:
            return []


# ============================================================================
# EMERGENCY CONTROLS
# ============================================================================

class EmergencyRateLimitControls:
    """Emergency controls for rate limiting."""

    @staticmethod
    async def enable_emergency_mode(redis_service, duration: int = 3600):
        """Enable emergency rate limiting (very strict limits)."""
        emergency_key = "emergency_mode:enabled"
        await redis_service.set(emergency_key, "true", expire=duration)

    @staticmethod
    async def disable_emergency_mode(redis_service):
        """Disable emergency rate limiting."""
        emergency_key = "emergency_mode:enabled"
        await redis_service.delete(emergency_key)

    @staticmethod
    async def is_emergency_mode(redis_service) -> bool:
        """Check if emergency mode is enabled."""
        emergency_key = "emergency_mode:enabled"
        return await redis_service.exists(emergency_key)

    @staticmethod
    async def block_ip(redis_service, ip: str, duration: int = 3600):
        """Block specific IP address."""
        block_key = f"blocked_ip:{ip}"
        await redis_service.set(block_key, "true", expire=duration)

    @staticmethod
    async def unblock_ip(redis_service, ip: str):
        """Unblock specific IP address."""
        block_key = f"blocked_ip:{ip}"
        await redis_service.delete(block_key)

    @staticmethod
    async def is_ip_blocked(redis_service, ip: str) -> bool:
        """Check if IP is blocked."""
        block_key = f"blocked_ip:{ip}"
        return await redis_service.exists(block_key)