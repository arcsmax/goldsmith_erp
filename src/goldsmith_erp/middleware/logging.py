"""
Logging middleware for request tracking.
"""
import logging
import time
import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from goldsmith_erp.core.logging import set_request_id, clear_request_id

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that logs all HTTP requests with timing and request IDs.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and add logging.
        
        Args:
            request: The incoming HTTP request
            call_next: The next middleware/handler
            
        Returns:
            Response: The HTTP response
        """
        # Generate unique request ID
        request_id = str(uuid.uuid4())
        set_request_id(request_id)
        
        # Add request ID to response headers for debugging
        start_time = time.time()
        
        # Log incoming request
        logger.info(
            "Incoming request",
            extra={
                "method": request.method,
                "url": str(request.url),
                "client_host": request.client.host if request.client else None,
                "user_agent": request.headers.get("user-agent"),
            }
        )
        
        try:
            # Process request
            response = await call_next(request)
            
            # Calculate processing time
            process_time = time.time() - start_time
            
            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = str(process_time)
            
            # Log response
            logger.info(
                "Request completed",
                extra={
                    "method": request.method,
                    "url": str(request.url),
                    "status_code": response.status_code,
                    "process_time_ms": round(process_time * 1000, 2),
                }
            )
            
            return response
            
        except Exception as exc:
            # Log error
            process_time = time.time() - start_time
            logger.error(
                "Request failed",
                extra={
                    "method": request.method,
                    "url": str(request.url),
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "process_time_ms": round(process_time * 1000, 2),
                },
                exc_info=True
            )
            raise
        finally:
            # Clear request ID from context
            clear_request_id()
