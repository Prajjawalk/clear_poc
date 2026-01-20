"""Utility functions for alerts app."""

from typing import Optional

from django.contrib.auth.models import User
from django.utils import timezone

from .models import Alert, UserAlert
from .exceptions import ValidationError, ValidationHelper


class UserAlertManager:
    """Utility class for managing UserAlert interactions."""

    @staticmethod
    def get_or_create_user_alert(user: User, alert: Alert) -> UserAlert:
        """
        Get or create a UserAlert for the given user and alert.

        This utility eliminates the repetitive pattern found in multiple views.
        """
        user_alert, created = UserAlert.objects.get_or_create(
            user=user,
            alert=alert,
            defaults={"received_at": timezone.now()}
        )
        return user_alert

    @staticmethod
    def mark_as_read(user: User, alert: Alert) -> UserAlert:
        """Mark an alert as read for the given user."""
        user_alert = UserAlertManager.get_or_create_user_alert(user, alert)

        if not user_alert.read_at:
            user_alert.read_at = timezone.now()
            user_alert.save(update_fields=["read_at"])

        return user_alert

    @staticmethod
    def toggle_bookmark(user: User, alert: Alert) -> tuple[UserAlert, bool]:
        """
        Toggle bookmark status for an alert.

        Returns:
            tuple: (user_alert, is_now_bookmarked)
        """
        user_alert = UserAlertManager.get_or_create_user_alert(user, alert)

        user_alert.bookmarked = not user_alert.bookmarked
        user_alert.save(update_fields=["bookmarked"])

        return user_alert, user_alert.bookmarked

    @staticmethod
    def set_rating(user: User, alert: Alert, rating: int) -> UserAlert:
        """Set a rating for an alert."""
        user_alert = UserAlertManager.get_or_create_user_alert(user, alert)

        user_alert.rating = rating
        user_alert.rating_at = timezone.now()
        user_alert.save(update_fields=["rating", "rating_at"])

        return user_alert

    @staticmethod
    def toggle_flag(user: User, alert: Alert, flag_type: str) -> tuple[UserAlert, bool]:
        """
        Toggle a flag (false or incomplete) for an alert.

        Args:
            flag_type: Either 'false' or 'incomplete'

        Returns:
            tuple: (user_alert, is_now_flagged)
        """
        user_alert = UserAlertManager.get_or_create_user_alert(user, alert)

        if flag_type == "false":
            user_alert.flag_false = not user_alert.flag_false
            field_name = "flag_false"
            is_flagged = user_alert.flag_false
        elif flag_type == "incomplete":
            user_alert.flag_incomplete = not user_alert.flag_incomplete
            field_name = "flag_incomplete"
            is_flagged = user_alert.flag_incomplete
        else:
            raise ValueError("flag_type must be 'false' or 'incomplete'")

        user_alert.save(update_fields=[field_name])

        return user_alert, is_flagged

    @staticmethod
    def add_comment(user: User, alert: Alert, comment: str) -> UserAlert:
        """Add a comment to an alert."""
        user_alert = UserAlertManager.get_or_create_user_alert(user, alert)

        user_alert.comment = comment
        user_alert.save(update_fields=["comment"])

        return user_alert

    @staticmethod
    def get_user_interaction(user: User, alert: Alert) -> Optional[UserAlert]:
        """Get existing user interaction for an alert, if any."""
        try:
            return UserAlert.objects.get(user=user, alert=alert)
        except UserAlert.DoesNotExist:
            return None


class AlertQueryBuilder:
    """Utility class for building common alert queries."""

    @staticmethod
    def get_approved_alerts_queryset():
        """Get base queryset for approved alerts with standard optimizations."""
        return Alert.objects.filter(
            go_no_go=True
        ).select_related(
            "shock_type", "data_source"
        ).prefetch_related("locations")

    @staticmethod
    def apply_common_filters(queryset, filters: dict):
        """
        Apply common filtering logic used across views and API endpoints.

        Args:
            queryset: Base alert queryset
            filters: Dictionary with filter parameters
                - shock_type: shock type ID
                - severity: severity level
                - date_from: start date filter
                - date_to: end date filter
                - search: text search in title/text
                - active_today: filter for currently active alerts
                - bookmarked: filter for user bookmarked alerts (requires user)

        Returns:
            Filtered queryset
        """
        from django.db.models import Q

        # Filter by shock type
        if filters.get("shock_type"):
            queryset = queryset.filter(shock_type_id=filters["shock_type"])

        # Filter by severity
        if filters.get("severity"):
            queryset = queryset.filter(severity=filters["severity"])

        # Filter by date range
        if filters.get("date_from"):
            queryset = queryset.filter(shock_date__gte=filters["date_from"])
        if filters.get("date_to"):
            queryset = queryset.filter(shock_date__lte=filters["date_to"])

        # Filter by active today
        if filters.get("active_today") and filters["active_today"] != "0":
            from django.utils import timezone
            today = timezone.now()
            queryset = queryset.filter(valid_from__lte=today, valid_until__gte=today)

        # Filter by bookmarked (requires user parameter)
        if filters.get("bookmarked") and filters.get("user"):
            queryset = queryset.filter(
                useralert__user=filters["user"],
                useralert__bookmarked=True
            )

        # Search in title and text
        if filters.get("search"):
            queryset = queryset.filter(
                Q(title__icontains=filters["search"]) |
                Q(text__icontains=filters["search"])
            )

        return queryset

    @staticmethod
    def add_user_interactions_prefetch(queryset, user: User):
        """Add prefetch for user interactions to avoid N+1 queries."""
        from django.db.models import Prefetch

        user_alerts_prefetch = Prefetch(
            'useralert_set',
            queryset=UserAlert.objects.filter(user=user),
            to_attr='user_interactions'
        )
        return queryset.prefetch_related(user_alerts_prefetch)

    @staticmethod
    def get_user_alert_from_prefetch(alert) -> Optional[UserAlert]:
        """Extract user alert from prefetched data."""
        if hasattr(alert, 'user_interactions') and alert.user_interactions:
            return alert.user_interactions[0]
        return None


class ResponseHelper:
    """Helper utilities for API responses."""

    @staticmethod
    def build_filter_context(request_get):
        """Build filter context for template rendering."""
        return {
            "shock_type": request_get.get("shock_type", ""),
            "severity": request_get.get("severity", ""),
            "date_from": request_get.get("date_from", ""),
            "date_to": request_get.get("date_to", ""),
            "active_today": request_get.get("active_today", "1"),
            "bookmarked": request_get.get("bookmarked", ""),
            "search": request_get.get("search", ""),
        }

    @staticmethod
    def validate_rating(rating_value) -> int:
        """Validate and convert rating value."""
        return ValidationHelper.validate_rating(rating_value)

    @staticmethod
    def validate_flag_type(flag_type: str) -> str:
        """Validate flag type parameter."""
        return ValidationHelper.validate_flag_type(flag_type)