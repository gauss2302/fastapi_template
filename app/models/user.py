from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, mapped_column, Mapped
from sqlalchemy.sql import func
from typing import Optional, List
from datetime import datetime
import uuid
import re

from app.core.database.database import Base
from app.models.applicant import Applicant
from app.models.application import ApplicationModel
from app.models.company import Company
from app.models.recruiter import Recruiter


class User(Base):
    """
    Базовая модель пользователя - для аутентификации и общих данных.
    Пользователь может иметь профили рекрутера и/или соискателя.
    """
    __tablename__ = "users"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )

    # Authentication fields
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False
    )
    hashed_password: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    # Profile information
    full_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )
    avatar_url: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )

    # OAuth providers
    google_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=True
    )
    github_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=True
    )

    # System fields
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True
    )
    is_superuser: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    last_login: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    # RELATIONSHIPS with proper typing
    applicant_profile: Mapped[Optional["Applicant"]] = relationship(
        "Applicant",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="select"
    )

    recruiter_profile: Mapped[Optional["Recruiter"]] = relationship(
        "Recruiter",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="select"
    )

    # Связь с заявками как соискатель
    applications: Mapped[List["ApplicationModel"]] = relationship(
        "Application",
        back_populates="user",
        lazy="select"
    )

    # Компании, которые верифицировал как админ
    verified_companies: Mapped[List["Company"]] = relationship(
        "Company",
        foreign_keys="Company.verified_by",
        lazy="select"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email})>"

    def __str__(self) -> str:
        return f"{self.display_name} ({self.email})"

    # User type properties
    @property
    def is_applicant(self) -> bool:
        """Проверить, является ли пользователь соискателем"""
        return self.applicant_profile is not None

    @property
    def is_recruiter(self) -> bool:
        """Проверить, является ли пользователь активным рекрутером"""
        return (
                self.recruiter_profile is not None and
                self.recruiter_profile.is_approved and
                self.recruiter_profile.is_active
        )

    @property
    def is_admin(self) -> bool:
        """Проверить, является ли пользователь администратором"""
        return self.is_superuser and self.is_active

    @property
    def user_types(self) -> List[str]:
        """Получить все типы пользователя"""
        types = []
        if self.is_applicant:
            types.append("applicant")
        if self.is_recruiter:
            types.append("recruiter")
        if self.is_superuser:
            types.append("admin")
        return types or ["user"]

    @property
    def primary_user_type(self) -> str:
        """Получить основной тип пользователя"""
        if self.is_superuser:
            return "admin"
        elif self.is_recruiter:
            return "recruiter"
        elif self.is_applicant:
            return "applicant"
        else:
            return "user"

    # Display properties
    @property
    def display_name(self) -> str:
        """Получить отображаемое имя пользователя"""
        if self.full_name and self.full_name.strip():
            return self.full_name.strip()
        return self.email.split('@')[0]

    @property
    def first_name(self) -> Optional[str]:
        """Получить имя пользователя"""
        if self.full_name:
            parts = self.full_name.strip().split()
            return parts[0] if parts else None
        return None

    @property
    def last_name(self) -> Optional[str]:
        """Получить фамилию пользователя"""
        if self.full_name:
            parts = self.full_name.strip().split()
            return parts[-1] if len(parts) > 1 else None
        return None

    @property
    def initials(self) -> str:
        """Получить инициалы пользователя"""
        if self.full_name:
            parts = self.full_name.strip().split()
            if len(parts) >= 2:
                return f"{parts[0][0]}{parts[-1][0]}".upper()
            elif len(parts) == 1:
                return parts[0][0].upper()
        return self.email[0].upper()

    # Authentication properties
    @property
    def has_password(self) -> bool:
        """Проверить, установлен ли пароль"""
        return self.hashed_password is not None

    @property
    def has_oauth_providers(self) -> bool:
        """Проверить, подключены ли OAuth провайдеры"""
        return self.google_id is not None or self.github_id is not None

    @property
    def oauth_providers(self) -> List[str]:
        """Получить список подключенных OAuth провайдеров"""
        providers = []
        if self.google_id:
            providers.append("google")
        if self.github_id:
            providers.append("github")
        return providers

    @property
    def is_email_verified(self) -> bool:
        """Проверить, верифицирован ли email"""
        return self.email_verified_at is not None

    @property
    def account_age_days(self) -> int:
        """Получить возраст аккаунта в днях"""
        return (datetime.utcnow() - self.created_at).days

    @property
    def is_new_user(self) -> bool:
        """Проверить, новый ли пользователь (регистрация < 7 дней)"""
        return self.account_age_days < 7

    @property
    def days_since_last_login(self) -> Optional[int]:
        """Дни с последнего входа"""
        if self.last_login:
            return (datetime.utcnow() - self.last_login).days
        return None

    @property
    def is_recently_active(self) -> bool:
        """Был ли пользователь активен в последние 30 дней"""
        days_since_login = self.days_since_last_login
        return days_since_login is not None and days_since_login <= 30

    # Profile completeness
    @property
    def profile_completeness(self) -> float:
        """Процент заполненности профиля (0.0 - 1.0)"""
        total_fields = 6
        completed_fields = 0

        # Обязательные поля
        if self.email:
            completed_fields += 1
        if self.full_name:
            completed_fields += 1

        # Дополнительные поля
        if self.avatar_url:
            completed_fields += 1
        if self.is_email_verified:
            completed_fields += 1
        if self.has_password or self.has_oauth_providers:
            completed_fields += 1

        # Профили
        if self.is_applicant or self.is_recruiter:
            completed_fields += 1

        return completed_fields / total_fields

    @property
    def is_profile_complete(self) -> bool:
        """Проверить, заполнен ли профиль (>= 80%)"""
        return self.profile_completeness >= 0.8

    # Business logic methods
    def update_last_login(self) -> None:
        """Обновить время последнего входа"""
        self.last_login = datetime.utcnow()

    def verify_email(self) -> None:
        """Верифицировать email"""
        self.email_verified_at = datetime.utcnow()
        self.is_verified = True

    def unverify_email(self) -> None:
        """Отменить верификацию email"""
        self.email_verified_at = None
        self.is_verified = False

    def activate(self) -> None:
        """Активировать пользователя"""
        self.is_active = True

    def deactivate(self) -> None:
        """Деактивировать пользователя"""
        self.is_active = False

    def make_superuser(self) -> None:
        """Сделать пользователя суперпользователем"""
        self.is_superuser = True

    def remove_superuser(self) -> None:
        """Убрать права суперпользователя"""
        self.is_superuser = False

    def link_google_account(self, google_id: str) -> None:
        """Привязать Google аккаунт"""
        self.google_id = google_id

    def unlink_google_account(self) -> None:
        """Отвязать Google аккаунт"""
        self.google_id = None

    def link_github_account(self, github_id: str) -> None:
        """Привязать GitHub аккаунт"""
        self.github_id = github_id

    def unlink_github_account(self) -> None:
        """Отвязать GitHub аккаунт"""
        self.github_id = None

    def update_profile(
            self,
            full_name: Optional[str] = None,
            avatar_url: Optional[str] = None
    ) -> None:
        """Обновить профиль пользователя"""
        if full_name is not None:
            self.full_name = full_name.strip() if full_name else None
        if avatar_url is not None:
            self.avatar_url = avatar_url

    # Validation methods
    def validate_email(self) -> List[str]:
        """Валидация email"""
        errors = []

        if not self.email:
            errors.append("Email is required")
            return errors

        # Базовая валидация email
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, self.email):
            errors.append("Invalid email format")

        if len(self.email) > 255:
            errors.append("Email is too long")

        return errors

    def validate_full_name(self) -> List[str]:
        """Валидация полного имени"""
        errors = []

        if self.full_name:
            if len(self.full_name) > 255:
                errors.append("Full name is too long")

            # Проверка на подозрительные символы
            if re.search(r'[<>{}[\]\\|`~]', self.full_name):
                errors.append("Full name contains invalid characters")

        return errors

    def get_validation_errors(self) -> List[str]:
        """Получить все ошибки валидации"""
        errors = []
        errors.extend(self.validate_email())
        errors.extend(self.validate_full_name())
        return errors

    def can_login(self) -> bool:
        """Проверить, может ли пользователь войти в систему"""
        return self.is_active and (self.has_password or self.has_oauth_providers)

    def can_access_admin(self) -> bool:
        """Проверить доступ к админ панели"""
        return self.is_active and self.is_superuser

    def can_recruit(self) -> bool:
        """Проверить, может ли пользователь заниматься рекрутингом"""
        return self.is_active and self.is_recruiter

    def can_apply_for_jobs(self) -> bool:
        """Проверить, может ли пользователь подавать заявки на работу"""
        return self.is_active and (self.is_applicant or not self.is_recruiter)

    # Query helpers (для использования в репозиториях)
    @classmethod
    def active_users_filter(cls):
        """Фильтр активных пользователей"""
        return cls.is_active == True

    @classmethod
    def verified_users_filter(cls):
        """Фильтр верифицированных пользователей"""
        return cls.is_verified == True

    @classmethod
    def superusers_filter(cls):
        """Фильтр суперпользователей"""
        return cls.is_superuser == True

    @classmethod
    def recent_users_filter(cls, days: int = 30):
        """Фильтр недавно зарегистрированных пользователей"""
        cutoff_date = datetime.utcnow() - datetime.timedelta(days=days)
        return cls.created_at >= cutoff_date

    @classmethod
    def oauth_users_filter(cls):
        """Фильтр пользователей с OAuth"""
        return (cls.google_id.isnot(None)) | (cls.github_id.isnot(None))

    # Security methods
    def get_security_context(self) -> dict:
        """Получить контекст безопасности пользователя"""
        return {
            "user_id": str(self.id),
            "email": self.email,
            "is_active": self.is_active,
            "is_verified": self.is_verified,
            "is_superuser": self.is_superuser,
            "user_types": self.user_types,
            "oauth_providers": self.oauth_providers,
            "created_at": self.created_at.isoformat(),
            "last_login": self.last_login.isoformat() if self.last_login else None
        }