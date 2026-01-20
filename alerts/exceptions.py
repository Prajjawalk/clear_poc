"""Custom exceptions and error handling for alerts app."""

import logging
from typing import Dict, Optional, Union

from django.core.exceptions import ValidationError
from django.http import JsonResponse

logger = logging.getLogger(__name__)


class AlertError(Exception):
    """Base exception for alert-related errors."""

    def __init__(self, message: str, code: str = "ALERT_ERROR", status_code: int = 400, details: Optional[Dict] = None):
        """
        Initialize alert error.

        Args:
            message: Human-readable error message
            code: Error code for programmatic handling
            status_code: HTTP status code
            details: Additional error details
        """
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class AlertNotFoundError(AlertError):
    """Exception raised when an alert cannot be found."""

    def __init__(self, alert_id: Union[int, str]):
        super().__init__(
            message=f"Alert with ID {alert_id} not found",
            code="ALERT_NOT_FOUND",
            status_code=404,
            details={"alert_id": str(alert_id)}
        )


class UserAlertError(AlertError):
    """Exception raised for user alert interaction errors."""

    def __init__(self, message: str, code: str = "USER_ALERT_ERROR", details: Optional[Dict] = None):
        super().__init__(message, code, 400, details)


class ValidationError(AlertError):
    """Exception raised for validation errors."""

    def __init__(self, field: str, message: str, value: Optional[str] = None):
        super().__init__(
            message=f"Validation error for {field}: {message}",
            code="VALIDATION_ERROR",
            status_code=422,
            details={"field": field, "value": value}
        )


class PermissionError(AlertError):
    """Exception raised for permission-related errors."""

    def __init__(self, message: str = "Permission denied"):
        super().__init__(
            message=message,
            code="PERMISSION_DENIED",
            status_code=403
        )


class RateLimitError(AlertError):
    """Exception raised when rate limits are exceeded."""

    def __init__(self, message: str = "Rate limit exceeded", retry_after: Optional[int] = None):
        details = {"retry_after": retry_after} if retry_after else {}
        super().__init__(
            message=message,
            code="RATE_LIMIT_EXCEEDED",
            status_code=429,
            details=details
        )


class APIErrorHandler:
    """Centralized error handling for API views."""

    @staticmethod
    def handle_error(error: Exception, request=None) -> JsonResponse:
        """
        Handle an exception and return appropriate JSON response.

        Args:
            error: The exception to handle
            request: Django request object (optional, for logging)

        Returns:
            JsonResponse with error details
        """
        if isinstance(error, AlertError):
            return APIErrorHandler._handle_alert_error(error, request)
        elif isinstance(error, ValidationError):
            return APIErrorHandler._handle_validation_error(error, request)
        elif isinstance(error, PermissionError):
            return APIErrorHandler._handle_permission_error(error, request)
        else:
            return APIErrorHandler._handle_unexpected_error(error, request)

    @staticmethod
    def _handle_alert_error(error: AlertError, request=None) -> JsonResponse:
        """Handle AlertError exceptions."""
        # Log the error
        if request:
            logger.warning(
                f"Alert error in {request.path}: {error.message}",
                extra={
                    "error_code": error.code,
                    "status_code": error.status_code,
                    "user": getattr(request, 'user', None),
                    "details": error.details
                }
            )

        return JsonResponse(
            {
                "success": False,
                "error": error.message,
                "code": error.code,
                "details": error.details
            },
            status=error.status_code
        )

    @staticmethod
    def _handle_validation_error(error: ValidationError, request=None) -> JsonResponse:
        """Handle Django validation errors."""
        if hasattr(error, 'message_dict'):
            # Form validation errors
            return JsonResponse(
                {
                    "success": False,
                    "error": "Validation failed",
                    "code": "VALIDATION_ERROR",
                    "details": {"fields": error.message_dict}
                },
                status=422
            )
        else:
            # Single validation error
            return JsonResponse(
                {
                    "success": False,
                    "error": str(error),
                    "code": "VALIDATION_ERROR"
                },
                status=422
            )

    @staticmethod
    def _handle_permission_error(error: PermissionError, request=None) -> JsonResponse:
        """Handle permission errors."""
        if request:
            logger.warning(
                f"Permission denied in {request.path}: {error}",
                extra={"user": getattr(request, 'user', None)}
            )

        return JsonResponse(
            {
                "success": False,
                "error": "Permission denied",
                "code": "PERMISSION_DENIED"
            },
            status=403
        )

    @staticmethod
    def _handle_unexpected_error(error: Exception, request=None) -> JsonResponse:
        """Handle unexpected errors."""
        # Log the full error for debugging
        if request:
            logger.error(
                f"Unexpected error in {request.path}: {error}",
                extra={"user": getattr(request, 'user', None)},
                exc_info=True
            )
        else:
            logger.error(f"Unexpected error: {error}", exc_info=True)

        # Return generic error response (don't expose internal details)
        return JsonResponse(
            {
                "success": False,
                "error": "An internal error occurred",
                "code": "INTERNAL_ERROR"
            },
            status=500
        )

    @staticmethod
    def success_response(data: Dict, message: str = "Success") -> JsonResponse:
        """Create a standardized success response."""
        return JsonResponse({
            "success": True,
            "message": message,
            **data
        })

    @staticmethod
    def paginated_response(items: list, page: int, total: int, pages: int,
                          has_next: bool, has_previous: bool, message: str = "Success") -> JsonResponse:
        """Create a standardized paginated response."""
        return JsonResponse({
            "success": True,
            "message": message,
            "count": len(items),
            "total": total,
            "page": page,
            "pages": pages,
            "has_next": has_next,
            "has_previous": has_previous,
            "results": items
        })


def api_error_handler(view_func):
    """
    Decorator to add consistent error handling to API views.

    Usage:
        @api_error_handler
        def my_api_view(request):
            # View code that might raise exceptions
            pass
    """
    def wrapper(request, *args, **kwargs):
        try:
            return view_func(request, *args, **kwargs)
        except Exception as e:
            return APIErrorHandler.handle_error(e, request)

    return wrapper


class ValidationHelper:
    """Helper class for common validation tasks."""

    @staticmethod
    def validate_rating(rating_value: Union[str, int]) -> int:
        """
        Validate rating value.

        Args:
            rating_value: Rating value to validate

        Returns:
            Validated integer rating

        Raises:
            ValidationError: If rating is invalid
        """
        try:
            rating = int(rating_value)
            if not (1 <= rating <= 5):
                raise ValidationError("rating", "Rating must be between 1 and 5", str(rating_value))
            return rating
        except (ValueError, TypeError):
            raise ValidationError("rating", "Rating must be a valid integer", str(rating_value))

    @staticmethod
    def validate_flag_type(flag_type: str) -> str:
        """
        Validate flag type value.

        Args:
            flag_type: Flag type to validate

        Returns:
            Validated flag type

        Raises:
            ValidationError: If flag type is invalid
        """
        valid_types = ["false", "incomplete"]
        if flag_type not in valid_types:
            raise ValidationError("flag_type", f"Flag type must be one of: {', '.join(valid_types)}", flag_type)
        return flag_type

    @staticmethod
    def validate_frequency(frequency: str) -> str:
        """
        Validate subscription frequency.

        Args:
            frequency: Frequency to validate

        Returns:
            Validated frequency

        Raises:
            ValidationError: If frequency is invalid
        """
        valid_frequencies = ["immediate", "daily", "weekly", "monthly"]
        if frequency not in valid_frequencies:
            raise ValidationError("frequency", f"Frequency must be one of: {', '.join(valid_frequencies)}", frequency)
        return frequency

    @staticmethod
    def validate_severity(severity_value: Union[str, int]) -> int:
        """
        Validate severity value.

        Args:
            severity_value: Severity value to validate

        Returns:
            Validated integer severity

        Raises:
            ValidationError: If severity is invalid
        """
        try:
            severity = int(severity_value)
            if not (1 <= severity <= 5):
                raise ValidationError("severity", "Severity must be between 1 and 5", str(severity_value))
            return severity
        except (ValueError, TypeError):
            raise ValidationError("severity", "Severity must be a valid integer", str(severity_value))

    @staticmethod
    def validate_positive_integer(field_name: str, value: Union[str, int]) -> int:
        """
        Validate positive integer value.

        Args:
            field_name: Name of the field being validated
            value: Value to validate

        Returns:
            Validated positive integer

        Raises:
            ValidationError: If value is invalid
        """
        # Check if value is a float (reject non-whole numbers)
        if isinstance(value, float):
            if value != int(value):
                raise ValidationError(field_name, f"{field_name} must be a whole number", str(value))

        try:
            int_value = int(value)
            if int_value <= 0:
                raise ValidationError(field_name, f"{field_name} must be a positive integer", str(value))
            return int_value
        except (ValueError, TypeError):
            raise ValidationError(field_name, f"{field_name} must be a valid integer", str(value))

    @staticmethod
    def validate_date_range(date_from: Optional[str], date_to: Optional[str]) -> Dict[str, Optional[str]]:
        """
        Validate date range parameters.

        Args:
            date_from: Start date (ISO format)
            date_to: End date (ISO format)

        Returns:
            Dictionary with validated dates

        Raises:
            ValidationError: If date format is invalid or range is invalid
        """
        from datetime import datetime

        validated = {"date_from": None, "date_to": None}

        if date_from:
            try:
                datetime.fromisoformat(date_from.replace("Z", "+00:00"))
                validated["date_from"] = date_from
            except ValueError:
                raise ValidationError("date_from", "Invalid date format. Use ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)", date_from)

        if date_to:
            try:
                datetime.fromisoformat(date_to.replace("Z", "+00:00"))
                validated["date_to"] = date_to
            except ValueError:
                raise ValidationError("date_to", "Invalid date format. Use ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)", date_to)

        # Validate range if both dates provided
        if validated["date_from"] and validated["date_to"]:
            from_date = datetime.fromisoformat(validated["date_from"].replace("Z", "+00:00"))
            to_date = datetime.fromisoformat(validated["date_to"].replace("Z", "+00:00"))
            if from_date > to_date:
                raise ValidationError("date_range", "date_from must be before date_to")

        return validated