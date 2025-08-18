import re
from typing import List, Optional


class PasswordValidator:
    MIN_LENGTH = 8
    MIN_UPPERCASE = 1
    MIN_LOWERCASE = 1
    MIN_DIGITS = 1
    MIN_SPECIAL_CHARS = 0  # Optional special characters

    SPECIAL_CHARS = "!@#$%^&*()_+-=[]{}|;:,.<>?"

    @classmethod
    def validate_password_strength(cls, password: str) -> tuple[bool, List[str]]:

        errors = []
        # Check uppercase letters
        uppercase_count = sum(1 for c in password if c.isupper())
        if uppercase_count < cls.MIN_UPPERCASE:
            errors.append(f"Password must contain at least {cls.MIN_UPPERCASE} uppercase letter(s)")

        # Check lowercase letters
        lowercase_count = sum(1 for c in password if c.islower())
        if lowercase_count < cls.MIN_LOWERCASE:
            errors.append(f"Password must contain at least {cls.MIN_LOWERCASE} lowercase letter(s)")

        # Check digits
        digit_count = sum(1 for c in password if c.isdigit())
        if digit_count < cls.MIN_DIGITS:
            errors.append(f"Password must contain at least {cls.MIN_DIGITS} digit(s)")

        # Check special characters (optional)
        if cls.MIN_SPECIAL_CHARS > 0:
            special_count = sum(1 for c in password if c in cls.SPECIAL_CHARS)
            if special_count < cls.MIN_SPECIAL_CHARS:
                errors.append(f"Password must contain at least {cls.MIN_SPECIAL_CHARS} special character(s)")

        cls._check_common_patterns(password, errors)

        return len(errors) == 0, errors

    @classmethod
    def _check_common_patterns(cls, password: str, errors: List[str]) -> None:
        """Check for common weak password patterns."""
        password_lower = password.lower()

        # Check for sequential characters
        if cls._has_sequential_chars(password_lower):
            errors.append("Password should not contain sequential characters (e.g., '123', 'abc')")

        # Check for repeated characters
        if cls._has_repeated_chars(password):
            errors.append("Password should not contain too many repeated characters")

        # Check against common weak passwords
        weak_passwords = {
            'password', 'password123', '12345678', 'qwerty', 'admin', 'letmein',
            'welcome', 'monkey', '123456789', 'qwerty123'
        }
        if password_lower in weak_passwords:
            errors.append("Password is too common and easily guessable")

    @classmethod
    def _has_sequential_chars(cls, password: str) -> bool:
        """Check if password contains sequential characters."""
        sequences = ['123456789', 'abcdefghijklmnopqrstuvwxyz', '987654321', 'zyxwvutsrqponmlkjihgfedcba']

        for seq in sequences:
            for i in range(len(seq) - 2):
                if seq[i:i + 3] in password:
                    return True
        return False

    @classmethod
    def _has_repeated_chars(cls, password: str) -> bool:
        """Check if password has too many repeated characters."""
        for i in range(len(password) - 2):
            if password[i] == password[i + 1] == password[i + 2]:
                return True
        return False

    @classmethod
    def get_password_strength_score(cls, password: str) -> tuple[int, str]:
        """
        Calculate password strength score (0-100) and description.

        Returns:
            tuple: (score, description)
        """
        score = 0

        # Length score (max 25 points)
        length_score = min(25, int(len(password) / 12) * 25)
        score += length_score

        # Character variety score (max 60 points)
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_special = any(c in cls.SPECIAL_CHARS for c in password)

        variety_score = sum([has_upper, has_lower, has_digit, has_special]) * 15
        score += variety_score

        # Uniqueness score (max 15 points)
        unique_chars = len(set(password))
        uniqueness_score = min(15, int(unique_chars / len(password)) * 15)
        score += uniqueness_score

        # Penalize common patterns
        is_valid, errors = cls.validate_password_strength(password)
        if not is_valid:
            score = max(0, score - (len(errors) * 10))

        # Determine strength description
        if score >= 80:
            description = "Very Strong"
        elif score >= 60:
            description = "Strong"
        elif score >= 40:
            description = "Moderate"
        elif score >= 20:
            description = "Weak"
        else:
            description = "Very Weak"

        return int(score), description


class EmailValidator:
    @classmethod
    def validate_email_format(cls, email: str) -> tuple[bool, Optional[str]]:
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

        if not re.match(email_pattern, email):
            return False, "Invalid Email Format"

        if '..' in email:
            return False, "Email cannot contain consecutive dots"

        local_part, domain = email.rsplit("@", 1)

        if not cls._validate_local_part(local_part):
            return False, "Invalid characters in email local part"

        if not cls._validate_domain_part(domain):
            return False, "Invalid domain format"

        return True, None

    @classmethod
    def _validate_domain_part(cls, domain: str) -> bool:
        if len(domain) > 255:
            return False

        if domain.startswith(".") or domain.endswith("."):
            return False

        labels = domain.split(".")
        for label in labels:
            if not label or len(label) > 63:
                return False
            if label.startswith("-") or label.endswith("-"):
                return False

        return True

    @classmethod
    def _validate_local_part(cls, local_part: str) -> bool:
        """Validate email local part (before @)."""
        if len(local_part) > 64:
            return False

        if local_part.startswith('.') or local_part.endswith('.'):
            return False

        return True


class UserDataValidator:
    """User data validation utilities."""

    @classmethod
    def validate_full_name(cls, full_name: str) -> tuple[bool, Optional[str]]:
        """
        Validate full name format.

        Returns:
            tuple: (is_valid, error_message)
        """
        if not full_name or not full_name.strip():
            return False, "Full name cannot be empty"

        if len(full_name.strip()) < 2:
            return False, "Full name must be at least 2 characters long"

        if len(full_name) > 100:
            return False, "Full name cannot exceed 100 characters"

        # Check for valid characters (letters, spaces, hyphens, apostrophes)
        if not re.match(r"^[a-zA-ZÀ-ÿ\s\-'\.]+$", full_name):
            return False, "Full name contains invalid characters"

        return True, None

    @classmethod
    def validate_avatar_url(cls, url: str) -> tuple[bool, Optional[str]]:
        """
        Validate avatar URL format.

        Returns:
            tuple: (is_valid, error_message)
        """
        if not url:
            return True, None  # Avatar URL is optional

        # Basic URL format check
        url_pattern = r'^https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)$'
        if not re.match(url_pattern, url):
            return False, "Invalid URL format"

        # Check if URL points to an image
        image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg')
        if not any(url.lower().endswith(ext) for ext in image_extensions):
            # Allow URLs without extensions (like Google profile pictures)
            if 'googleusercontent.com' not in url and 'gravatar.com' not in url:
                return False, "URL must point to an image file"

        return True, None


def validate_password(v: str) -> str:
    """Pydantic validator for password"""
    is_valid, errors = PasswordValidator.validate_password_strength(v)
    if not is_valid:
        raise ValueError('; '.join(errors))


def validate_email(v: str) -> str:
    """Pydantic validator for email."""
    is_valid, error = EmailValidator.validate_email_format(v)
    if not is_valid:
        raise ValueError(error)
    return v


def validate_full_name(v: str) -> str:
    """Pydantic validator for full name."""
    if v is None:
        return str(v)

    is_valid, error = UserDataValidator.validate_full_name(v)
    if not is_valid:
        raise ValueError(error)
    return v.strip()


def validate_avatar_url(v: str) -> str:
    """Pydantic validator for avatar URL."""
    if v is None:
        return str(v)

    is_valid, error = UserDataValidator.validate_avatar_url(v)
    if not is_valid:
        raise ValueError(error)
    return v
