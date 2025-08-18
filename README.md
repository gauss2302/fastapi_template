# FastAPI Backend

Продуктовый бэкенд на FastAPI с PostgreSQL, Redis и Google OAuth аутентификацией.

## Особенности

- 🚀 **FastAPI** с async/await поддержкой
- 🐘 **PostgreSQL** с SQLAlchemy 2.0 и Alembic миграциями
- 🔴 **Redis** для кэширования и сессий
- 🔐 **Google OAuth 2.0** аутентификация с JWT токенами
- 🏗️ **Clean Architecture** с разделением слоев
- 📝 **Pydantic** для валидации данных
- 🐳 **Docker** и docker-compose для разработки
- 🧪 **Pytest** для тестирования
- 📊 **Structured logging** с structlog
- 🔒 **Безопасность**: CORS, rate limiting, защищенные endpoints
- 📚 **Автоматическая документация** API (Swagger/OpenAPI)

## Архитектура

```
app/
├── api/           # API endpoints и роуты
├── core/          # Конфигурация, база данных, безопасность
├── models/        # SQLAlchemy модели
├── repositories/  # Слой доступа к данным
├── schemas/       # Pydantic схемы
└── services/      # Бизнес-логика
```

## Быстрый старт

### 1. Клонирование и установка

```bash
git clone <repository>
cd fastapi-backend
cp .env.example .env
```

### 2. Настройка Google OAuth

1. Перейдите в [Google Cloud Console](https://console.cloud.google.com/)
2. Создайте новый проект или выберите существующий
3. Включите Google+ API
4. Создайте OAuth 2.0 credentials
5. Добавьте redirect URI: `http://localhost:8000/api/v1/auth/google/callback`
6. Обновите `.env` файл с вашими Google credentials

### 3. Запуск с Docker

```bash
# Запуск всех сервисов
docker-compose up -d

# Применение миграций
docker-compose exec api poetry run alembic upgrade head

# Просмотр логов
docker-compose logs -f api
```

### 4. Альтернативный запуск (без Docker)

```bash
# Установка зависимостей
poetry install

# Запуск PostgreSQL и Redis локально
# ... настройте по вашему предпочтению

# Применение миграций
poetry run alembic upgrade head

# Запуск приложения
poetry run uvicorn app.main:app --reload
```

## Использование API

### Аутентификация

1. **Инициация Google OAuth:**
```bash
GET /api/v1/auth/google/login
```

2. **Аутентификация с кодом:**
```bash
POST /api/v1/auth/google/token
{
  "code": "authorization_code_from_google"
}
```

3. **Обновление токена:**
```bash
POST /api/v1/auth/refresh
{
  "refresh_token": "your_refresh_token"
}
```

### Защищенные endpoints

```bash
# Получение профиля
GET /api/v1/users/me
Authorization: Bearer your_access_token

# Обновление профиля
PUT /api/v1/users/me
Authorization: Bearer your_access_token
{
  "full_name": "New Name"
}
```

## Переменные окружения

Основные переменные в `.env`:

```env
# Безопасность
SECRET_KEY=your-secret-key
ACCESS_TOKEN_EXPIRE_MINUTES=30

# База данных
POSTGRES_SERVER=localhost
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=fastapi_db

# Redis
REDIS_URL=redis://localhost:6379/0

# Google OAuth
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret
```

## Миграции базы данных

```bash
# Создание миграции
poetry run alembic revision --autogenerate -m "Description"

# Применение миграций
poetry run alembic upgrade head

# Откат миграции
poetry run alembic downgrade -1
```

## Тестирование

```bash
# Запуск всех тестов
poetry run pytest

# Запуск с покрытием
poetry run pytest --cov=app --cov-report=html

# Запуск конкретного теста
poetry run pytest tests/test_auth.py::test_google_login
```

## Мониторинг и логи

- **Документация API**: http://localhost:8000/api/v1/docs
- **Health check**: http://localhost:8000/health
- **pgAdmin**: http://localhost:5050 (admin@example.com / admin)
- **Логи**: `docker-compose logs -f api`

## Производственный деплой

1. Измените `DEBUG=false` в `.env`
2. Используйте сильный `SECRET_KEY`
3. Настройте HTTPS
4. Обновите `BACKEND_CORS_ORIGINS`
5. Настройте мониторинг и логи
6. Используйте managed базы данных (PostgreSQL, Redis)

## Разработка

### Структура проекта

- **SOLID принципы**: Каждый класс имеет одну ответственность
- **DRY**: Отсутствие дублирования кода
- **Clean Architecture**: Разделение на слои (API → Services → Repositories → Models)
- **Dependency Injection**: Использование FastAPI dependencies

### Добавление новых функций

1. Создайте модель в `app/models/`
2. Добавьте схемы в `app/schemas/`
3. Создайте репозиторий в `app/repositories/`
4. Добавьте бизнес-логику в `app/services/`
5. Создайте API endpoints в `app/api/v1/endpoints/`
6. Добавьте тесты в `tests/`

### Code Style

```bash
# Форматирование кода
poetry run black .
poetry run isort .

# Линтинг
poetry run flake8
poetry run mypy .
```

## Лицензия

MIT License