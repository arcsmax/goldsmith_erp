"""
Structured logging configuration for Goldsmith ERP.

Provides JSON-formatted logs with request IDs for traceability.
"""
import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Optional

from pythonjsonlogger import jsonlogger

from goldsmith_erp.core.config import settings

# Context variable to store request ID for the current request
request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """
    Custom JSON formatter that includes request_id in every log entry.
    """

    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        
        # Add request ID if available
        request_id = request_id_ctx.get()
        if request_id:
            log_record["request_id"] = request_id
        
        # Add standard fields
        log_record["timestamp"] = self.formatTime(record, self.datefmt)
        log_record["level"] = record.levelname
        log_record["logger"] = record.name
        
        # Add source location for non-INFO logs
        if record.levelno > logging.INFO:
            log_record["file"] = record.pathname
            log_record["line"] = record.lineno
            log_record["function"] = record.funcName


def setup_logging() -> None:
    """
    Configure structured logging for the application.
    
    - JSON format for easy parsing by log aggregators
    - Request IDs for request tracing
    - Different log levels based on DEBUG setting
    """
    # Determine log level
    log_level = logging.DEBUG if settings.DEBUG else logging.INFO
    
    # Create JSON formatter
    formatter = CustomJsonFormatter(
        "%(timestamp)s %(level)s %(logger)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Add console handler with JSON formatter
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)
    root_logger.addHandler(console_handler)
    
    # Set specific loggers to appropriate levels
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)  # Reduce noise
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.DEBUG else logging.WARNING
    )
    
    # Log startup message
    logger = logging.getLogger(__name__)
    logger.info(
        "Structured logging initialized",
        extra={
            "debug_mode": settings.DEBUG,
            "log_level": logging.getLevelName(log_level)
        }
    )


def get_request_id() -> str:
    """
    Get the current request ID or generate a new one.
    
    Returns:
        str: The current request ID
    """
    request_id = request_id_ctx.get()
    if not request_id:
        request_id = str(uuid.uuid4())
        request_id_ctx.set(request_id)
    return request_id


def set_request_id(request_id: str) -> None:
    """
    Set the request ID for the current context.
    
    Args:
        request_id: The request ID to set
    """
    request_id_ctx.set(request_id)


def clear_request_id() -> None:
    """
    Clear the request ID from the current context.
    """
    request_id_ctx.set(None)
