FROM python:3.13-slim

# Env
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache \
    PATH="/app/.venv/bin:$PATH"

# System deps - добавлен libpq-dev для psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Poetry
RUN pip install --no-cache-dir poetry

WORKDIR /app

# Только файлы зависимостей — для кэша слоёв
COPY pyproject.toml poetry.lock* ./

# Установка зависимостей (включая dev зависимости для alembic)
RUN poetry install --no-root && rm -rf $POETRY_CACHE_DIR

# Теперь код приложения
COPY . .

# Убедимся что alembic установлен
RUN poetry run pip list | grep alembic

# Непривилегированный пользователь
RUN adduser --disabled-password --gecos '' --shell /bin/bash user \
    && chown -R user:user /app
USER user

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
  CMD curl -fsS http://localhost:8000/health || exit 1

# Используем poetry run для запуска uvicorn
CMD ["poetry", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]