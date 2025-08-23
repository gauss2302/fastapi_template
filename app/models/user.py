from sqlalchemy import Boolean, Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )
    email = Column(String(255), unique=True, index=True, nullable=False)
    full_name = Column(String(255), nullable=True)
    avatar_url = Column(Text, nullable=True)
    hashed_password = Column(String(255), nullable=True)

    google_id = Column(String(255), unique=True, index=True, nullable=True)
    github_id = Column(String(255), unique=True, index=True, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    last_login = Column(DateTime(timezone=True), nullable=True)

    # Опциональная связь с recruiter - может быть None для обычных пользователей
    recruiter_profile = relationship(
        "Recruiter",
        back_populates="user",
        uselist=False,  # One-to-one relationship
        cascade="all, delete-orphan",
        lazy="select"  # Не загружать автоматически
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email})>"

    @property
    def is_recruiter(self) -> bool:
        """Проверить, является ли пользователь рекрутером"""
        return self.recruiter_profile is not None

    @property
    def user_type(self) -> str:
        """Получить тип пользователя"""
        return "recruiter" if self.is_recruiter else "user"