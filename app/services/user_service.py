from typing import Optional
from uuid import UUID
from datetime import datetime

from app.repositories.user_repository import UserRepository
from app.services.auth_service import GoogleOAuthService
from app.schemas.user import (
    User,
    UserCreate,
    UserUpdate,
    UserRegister,
    UserLogin,
    UserPasswordUpdate,
    GoogleUserInfo,
    Token,
)
from app.core.security import security_service
from app.core.exceptions import NotFoundError, AuthenticationError, ConflictError


class UserService:
    def __init__(
            self,
            user_repo: UserRepository,
            google_oauth_service: GoogleOAuthService,
    ):
        self.user_repo = user_repo
        self.google_oauth_service = google_oauth_service

    async def register_user(self, user_data: UserRegister) -> User:
        """Register a new user with email and password."""
        db_user = await self.user_repo.create_user_with_password(user_data)
        return User.model_validate(db_user)

    async def authenticate_user(self, login_data: UserLogin) -> tuple[User, Token]:
        """Authenticate user with email and password."""
        db_user = await self.user_repo.authenticate_user(
            login_data.email, login_data.password
        )

        if not db_user:
            raise AuthenticationError("Invalid email or password")

        if not db_user.is_active:
            raise AuthenticationError("User account is deactivated")

        # Update last login
        await self.user_repo.update_last_login(db_user.id)

        # Generate tokens
        tokens = security_service.create_token_pair(db_user.id)

        # Cache refresh token
        await self.google_oauth_service.cache_refresh_token(
            str(db_user.id), tokens["refresh_token"]
        )

        user = User.model_validate(db_user)
        token = Token(**tokens)

        return user, token

    async def create_user(self, user_data: UserCreate) -> User:
        """Create a new user."""
        db_user = await self.user_repo.create(user_data)
        return User.model_validate(db_user)

    async def get_user_by_id(self, user_id: UUID) -> Optional[User]:
        """Get user by ID."""
        db_user = await self.user_repo.get_by_id(user_id)
        if db_user:
            return User.model_validate(db_user)
        return None

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email."""
        db_user = await self.user_repo.get_by_email(email)
        if db_user:
            return User.model_validate(db_user)
        return None

    async def update_user(self, user_id: UUID, user_data: UserUpdate) -> User:
        """Update user."""
        db_user = await self.user_repo.update(user_id, user_data)
        return User.model_validate(db_user)

    async def update_password(self, user_id: UUID, password_data: UserPasswordUpdate) -> bool:
        """Update user password."""
        # Get current user
        db_user = await self.user_repo.get_by_id(user_id)
        if not db_user:
            raise NotFoundError("User not found")

        # Verify current password
        if not db_user.hashed_password:
            raise AuthenticationError("User has no password set")

        if not security_service.verify_password(
                password_data.current_password, db_user.hashed_password
        ):
            raise AuthenticationError("Current password is incorrect")

        # Update password
        await self.user_repo.update_password(user_id, password_data.new_password)
        return True

    async def delete_user(self, user_id: UUID) -> bool:
        """Soft delete user."""
        return await self.user_repo.delete(user_id)

    async def authenticate_with_google(
            self, google_user_info: GoogleUserInfo
    ) -> tuple[User, Token]:
        """Authenticate or register user with Google OAuth."""
        # Try to find existing user by Google ID
        db_user = await self.user_repo.get_by_google_id(google_user_info.id)

        if not db_user:
            # Try to find user by email
            db_user = await self.user_repo.get_by_email(google_user_info.email)

            if db_user:
                # Link Google account to existing user
                db_user = await self.user_repo.link_google_account(
                    db_user.id, google_user_info.id
                )
            else:
                # Create new user
                user_create = UserCreate(
                    email=google_user_info.email,
                    full_name=google_user_info.name,
                    avatar_url=google_user_info.picture,
                    google_id=google_user_info.id,
                    password=""  # No password for Google users
                )
                db_user = await self.user_repo.create(user_create)

        if not db_user.is_active:
            raise AuthenticationError("User account is deactivated")

        # Update last login
        await self.user_repo.update_last_login(db_user.id)

        # Generate tokens
        tokens = security_service.create_token_pair(db_user.id)

        # Cache refresh token
        await self.google_oauth_service.cache_refresh_token(
            str(db_user.id), tokens["refresh_token"]
        )

        user = User.model_validate(db_user)
        token = Token(**tokens)

        return user, token

    async def link_google_account(
            self, user_id: UUID, google_user_info: GoogleUserInfo
    ) -> User:
        """Link Google account to existing user."""
        # Check if Google account is already linked to another user
        existing_google_user = await self.user_repo.get_by_google_id(google_user_info.id)
        if existing_google_user and existing_google_user.id != user_id:
            raise ConflictError("Google account is already linked to another user")

        # Check if email matches
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError("User not found")

        if user.email != google_user_info.email:
            raise ConflictError("Google account email does not match user email")

        # Link Google account
        db_user = await self.user_repo.link_google_account(user_id, google_user_info.id)
        return User.model_validate(db_user)

    async def refresh_token(self, refresh_token: str) -> Token:
        """Refresh access token using refresh token."""
        # Verify refresh token
        payload = security_service.verify_token(refresh_token)
        if not payload or not payload.sub:
            raise AuthenticationError("Invalid refresh token")

        # Check if token is in cache
        cached_token = await self.google_oauth_service.get_refresh_token(payload.sub)
        if not cached_token or cached_token != refresh_token:
            raise AuthenticationError("Refresh token not found or invalid")

        # Check if user exists and is active
        user_id = UUID(payload.sub)
        db_user = await self.user_repo.get_by_id(user_id)
        if not db_user or not db_user.is_active:
            raise AuthenticationError("User not found or inactive")

        # Generate new tokens
        tokens = security_service.create_token_pair(user_id)

        # Update cached refresh token
        await self.google_oauth_service.cache_refresh_token(
            str(user_id), tokens["refresh_token"]
        )

        return Token(**tokens)

    async def logout(self, user_id: UUID) -> bool:
        """Logout user by revoking refresh token."""
        await self.google_oauth_service.revoke_refresh_token(str(user_id))
        return True

    async def activate_user(self, user_id: UUID) -> bool:
        """Activate user account."""
        return await self.user_repo.activate_user(user_id)

    async def deactivate_user(self, user_id: UUID) -> bool:
        """Deactivate user account."""
        return await self.user_repo.deactivate_user(user_id)

    async def get_user_stats(self) -> dict:
        """Get user statistics."""
        active_users_count = await self.user_repo.get_active_users_count()
        return {
            "active_users": active_users_count,
            "timestamp": datetime.utcnow(),
        }