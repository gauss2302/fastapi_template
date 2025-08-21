from datetime import datetime
from sqlalchemy import update, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Optional
from uuid import UUID

from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import security_service
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate, UserRegister


class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, user_data: UserCreate) -> User:
        """Create a new user."""
        existing_user = await self.get_by_email(user_data.email)
        if existing_user:
            raise ConflictError(f"User with email {user_data.email} already exists")

        if user_data.google_id:
            existing_google_user = await self.get_by_google_id(user_data.google_id)
            if existing_google_user:
                raise ConflictError("Google account already linked to another user")

        user_dict = user_data.model_dump()
        if 'password' in user_dict and user_dict['password']:
            user_dict['hashed_password'] = security_service.get_password_hash(user_dict['password'])
            del user_dict['password']

        db_user = User(**user_dict)
        self.db.add(db_user)
        await self.db.flush()
        await self.db.refresh(db_user)
        return db_user

    async def create_user_with_password(self, user_data: UserRegister) -> User:
        """Create a new user with password."""
        existing_user = await self.get_by_email(user_data.email)
        if existing_user:
            raise ConflictError(f"User with email {user_data.email} already exists")

        hashed_password = security_service.get_password_hash(user_data.password)

        db_user = User(
            email=user_data.email,
            full_name=user_data.full_name,
            hashed_password=hashed_password,
            is_active=True
        )

        self.db.add(db_user)
        await self.db.flush()
        await self.db.refresh(db_user)
        return db_user

    async def create_with_github(self, user_data: UserCreate) -> User:
        """Create a new user with GitHub OAuth data."""
        return await self.create(user_data)


    async def get_by_id(self, user_id: UUID) -> Optional[User]:
        """Get a user by ID"""
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[User]:
        """Get user by email."""
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_google_id(self, google_id: str) -> Optional[User]:
        """Get user by Google ID"""
        result = await self.db.execute(
            select(User).where(User.google_id == google_id)
        )
        return result.scalar_one_or_none()

    async def get_by_github_id(self, github_id: str) -> Optional[User]:
        result = await self.db.execute(
            select(User).where(User.github_id == github_id)
        )

        return result.scalar_one_or_none()

    async def authenticate_user(self, email: str, password: str) -> Optional[User]:
        """Authenticate user with email and password."""
        user = await self.get_by_email(email)
        if not user or not user.hashed_password:
            return None

        if not security_service.verify_password(password, user.hashed_password):
            return None

        return user

    async def update(self, user_id: UUID, user_data: UserUpdate) -> User:
        """Update user."""
        user = await self.get_by_id(user_id)
        if not user:
            raise NotFoundError("User not found")

        # Check email uniqueness if email is being updated
        if user_data.email and user_data.email != user.email:
            existing_user = await self.get_by_email(user_data.email)
            if existing_user:
                raise ConflictError(f"User with email {user_data.email} already exists")

        update_data = user_data.model_dump(exclude_unset=True)
        if update_data:
            update_data["updated_at"] = datetime.utcnow()
            stmt = (
                update(User)
                .where(User.id == user_id)
                .values(**update_data)
            )
            await self.db.execute(stmt)
            await self.db.refresh(user)

        return user

    async def delete(self, user_id: UUID) -> bool:
        """Delete user (soft delete by setting is_active to False)."""
        user = await self.get_by_id(user_id)
        if not user:
            return False

        user.is_active = False
        user.updated_at = datetime.utcnow()
        return True

    async def update_password(self, user_id: UUID, new_password: str) -> User:
        """Update user password."""
        user = await self.get_by_id(user_id)
        if not user:
            raise NotFoundError("User not found")

        hashed_password = security_service.get_password_hash(new_password)
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(
                hashed_password=hashed_password,
                updated_at=datetime.utcnow()
            )
        )
        await self.db.execute(stmt)
        await self.db.refresh(user)
        return user

    async def update_last_login(self, user_id: UUID) -> None:
        """Update the last login timestamp"""
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(last_login=datetime.utcnow(), updated_at=datetime.utcnow())
        )
        await self.db.execute(stmt)

    async def activate_user(self, user_id: UUID) -> bool:
        """Activate user account"""
        user = await self.get_by_id(user_id)
        if not user:
            return False
        user.is_active = True
        user.updated_at = datetime.utcnow()
        return True

    async def deactivate_user(self, user_id: UUID) -> bool:
        """Deactivate user account"""
        user = await self.get_by_id(user_id)
        if not user:
            return False
        user.is_active = False
        user.updated_at = datetime.utcnow()
        return True

    async def get_active_users_count(self) -> int:
        """Get the number of active users"""
        result = await self.db.execute(
            select(func.count(User.id)).where(User.is_active == True)
        )
        return result.scalar() or 0

    async def link_google_account(self, user_id: UUID, google_id: str) -> User:
        """Link google account to user"""
        user = await self.get_by_id(user_id)
        if not user:
            raise NotFoundError("User not found")

        existing_google_user = await self.get_by_google_id(google_id)
        if existing_google_user and existing_google_user.id != user_id:
            raise ConflictError("Google account already linked to another user")

        user.google_id = google_id
        user.updated_at = datetime.utcnow()
        return user


    async def link_github_account(self, user_id: UUID, github_id: str) -> User:
        user = await self.get_by_id(user_id)
        if not user:
            raise NotFoundError("User not found")

        existing_github_user = await self.get_by_github_id(github_id)
        if existing_github_user and existing_github_user.id != user_id:
            raise ConflictError("GitHub account already linked to another user")

        user.github_id = github_id
        user.updated_at = datetime.utcnow()

        return user

    async def unlink_github_account(self, user_id: UUID) -> bool:
        user = await self.get_by_id(user_id)
        if not user:
            return False

        user.github_id = None
        user.updated_at = datetime.utcnow()
        return True