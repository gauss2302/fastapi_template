from typing import Dict, Any

import structlog
import logging
import sys
from pathlib import Path
from uuid import UUID
from datetime import datetime

from app.core.config import settings


def config_structlog():
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if settings.DEBUG:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    )


class AppLogger:
    def __init__(self, name: str, **default_context):
        self.logger = structlog.get_logger(name)
        self.default_context = default_context

    def _clean_context(self, **kwargs) -> Dict[str, Any]:
        clean_context = {**self.default_context}

        for key, value in kwargs.items():
            if isinstance(value, (UUID, datetime)):
                clean_context[key] = str(value)
            elif hasattr(value, 'model_dump'):
                clean_context[key] = value.model_dump()
            else:
                clean_context[key] = value

        return clean_context

    def debug(self, message: str, **kwargs):
        """Debug логирование"""
        context = self._clean_context(**kwargs)
        self.logger.debug(message, **context)

    def info(self, message: str, **kwargs):
        """Info логирование"""
        context = self._clean_context(**kwargs)
        self.logger.info(message, **context)

    def warning(self, message: str, **kwargs):
        """Warning логирование"""
        context = self._clean_context(**kwargs)
        self.logger.warning(message, **context)

    def error(self, message: str, **kwargs):
        """Error логирование"""
        context = self._clean_context(**kwargs)
        self.logger.error(message, **context)

    def critical(self, message: str, **kwargs):
        """Critical логирование"""
        context = self._clean_context(**kwargs)
        self.logger.critical(message, **context)

    def exception(self, message: str, **kwargs):
        """Логирование исключений с трейсбеком"""
        context = self._clean_context(**kwargs)
        self.logger.exception(message, **context)

    def bind(self, **context):
        """Создание логгера с дополнительным контекстом"""
        new_context = {**self.default_context, **context}
        return AppLogger(self.logger.name, **new_context)
