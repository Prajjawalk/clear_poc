"""Abstract base class for data source implementations."""

import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Optional

from django.contrib.auth.models import User
from django.db import models
from django.urls import reverse
from django.utils import timezone

from location.models import Location

from .models import Variable, VariableData


class Source(ABC):
    """Abstract base class for data source implementations.

    Each data source provider should implement this class to provide
    standardized data retrieval, processing, and aggregation methods.
    """

    def __init__(self, source_model: "Source"):
        """Initialize source with database model instance."""
        self.source_model = source_model
        self.logger = logging.getLogger(f"data_pipeline.{source_model.class_name}")

    @abstractmethod
    def get(self, variable: Variable, **kwargs) -> bool:
        """Retrieve raw data for a variable from the source.

        Args:
            variable: Variable instance to retrieve data for
            **kwargs: Additional parameters for data retrieval

        Returns:
            bool: True if data retrieval was successful, False otherwise

        This method should:
        1. Connect to the data source
        2. Retrieve raw data for the specified variable
        3. Store raw data on filesystem
        4. Return success/failure status
        """
        pass

    @abstractmethod
    def process(self, variable: Variable, **kwargs) -> bool:
        """Process raw data into standardized format.

        Args:
            variable: Variable instance to process data for
            **kwargs: Additional parameters for data processing

        Returns:
            bool: True if processing was successful, False otherwise

        This method should:
        1. Read raw data from filesystem
        2. Parse and validate the data
        3. Match locations using gazetteer
        4. Convert to standardized format
        5. Store processed data in database using VariableData model
        """
        pass

    def get_all_variables(self, **kwargs) -> bool:
        """Retrieve raw data for ALL variables from this source's endpoint in one call.

        This method should be overridden by sources that can efficiently retrieve
        data for multiple variables in a single API call.

        Args:
            **kwargs: Additional parameters for data retrieval

        Returns:
            bool: True if data retrieval was successful, False otherwise

        Default implementation calls get() for each variable individually.
        """
        variables = self.source_model.variables.all()
        success_count = 0

        for variable in variables:
            if self.get(variable, **kwargs):
                success_count += 1

        return success_count > 0

    def process_all_variables(self, **kwargs) -> bool:
        """Process raw data into standardized format for ALL variables.

        This method should be overridden by sources that process data for
        multiple variables from a single raw data source.

        Args:
            **kwargs: Additional parameters for data processing

        Returns:
            bool: True if processing was successful, False otherwise

        Default implementation calls process() for each variable individually.
        """
        variables = self.source_model.variables.all()
        success_count = 0

        for variable in variables:
            if self.process(variable, **kwargs):
                success_count += 1

        processing_successful = success_count > 0

        # Send notification about unmatched locations if processing was successful
        if processing_successful:
            self.notify_unmatched_locations_summary()

        return processing_successful

    def aggregate(
        self,
        variable: Variable,
        target_period: str | None = None,
        target_adm_level: int | None = None,
        **kwargs,
    ) -> bool:
        """Aggregate processed data to different temporal/geographic levels.

        Args:
            variable: Variable instance to aggregate data for
            target_period: Target period type (day, week, month, quarter, year)
            target_adm_level: Target administrative level (0, 1, 2, etc.)
            **kwargs: Additional parameters for aggregation

        Returns:
            bool: True if aggregation was successful, False otherwise

        Default implementation performs simple sum aggregation.
        Override for more complex aggregation logic.
        """
        try:
            self.logger.info(f"Starting aggregation for {variable.code}")

            # Get source data
            source_data = VariableData.objects.filter(variable=variable)

            if target_period:
                source_data = source_data.filter(period__in=self._get_source_periods(target_period))

            if target_adm_level is not None:
                # Aggregate geographically
                return self._aggregate_geographically(variable, source_data, target_adm_level)

            if target_period:
                # Aggregate temporally
                return self._aggregate_temporally(variable, source_data, target_period)

            self.logger.warning("No aggregation parameters specified")
            return False

        except Exception as e:
            self.logger.error(f"Aggregation failed for {variable.code}: {str(e)}")
            return False

    def _aggregate_geographically(
        self,
        variable: Variable,
        source_data: models.QuerySet,
        target_adm_level: int,
    ) -> bool:
        """Aggregate data to higher administrative level."""
        # Get locations at target level
        target_locations = Location.objects.filter(admin_level__code=str(target_adm_level))

        aggregated_count = 0

        for location in target_locations:
            # Get child locations
            child_locations = location.get_descendants()

            # Aggregate data from child locations
            location_data = source_data.filter(gid__in=child_locations)

            if not location_data.exists():
                continue

            # Group by date period and sum values
            date_groups = {}
            for data in location_data:
                key = (data.start_date, data.end_date, data.period)
                if key not in date_groups:
                    date_groups[key] = {"value": 0, "text_parts": []}

                if data.value is not None:
                    date_groups[key]["value"] += data.value

                if data.text:
                    date_groups[key]["text_parts"].append(data.text)

            # Create aggregated records
            for (start_date, end_date, period), aggregated in date_groups.items():
                VariableData.objects.update_or_create(
                    variable=variable,
                    start_date=start_date,
                    end_date=end_date,
                    gid=location,
                    defaults={
                        "period": period,
                        "adm_level": location.admin_level,
                        "value": aggregated["value"] if aggregated["value"] > 0 else None,
                        "text": " | ".join(aggregated["text_parts"]) if aggregated["text_parts"] else "",
                        "updated_at": timezone.now(),
                    },
                )
                aggregated_count += 1

        self.logger.info(f"Created {aggregated_count} aggregated records")
        return aggregated_count > 0

    def _aggregate_temporally(self, variable: Variable, source_data: models.QuerySet, target_period: str) -> bool:
        """Aggregate data to different temporal frequency."""
        # This is a simplified implementation
        # Real implementation would need proper date grouping logic
        self.logger.info(f"Temporal aggregation to {target_period} not fully implemented")
        return True

    def _get_source_periods(self, target_period: str) -> list[str]:
        """Get list of source periods that can aggregate to target period."""
        period_hierarchy = ["day", "week", "month", "quarter", "year"]

        try:
            target_index = period_hierarchy.index(target_period)
            return period_hierarchy[: target_index + 1]
        except ValueError:
            return [target_period]

    # Token Management Methods

    def get_auth_token(self) -> Optional["SourceAuthToken"]:
        """Get the stored authentication token for this source."""
        try:
            from .models import SourceAuthToken

            return SourceAuthToken.objects.get(source=self.source_model)
        except SourceAuthToken.DoesNotExist:
            return None

    def store_auth_token(
        self,
        access_token: str,
        refresh_token: str = "",
        token_type: str = "Bearer",
        expires_in: int | None = None,
        refresh_expires_in: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "SourceAuthToken":
        """Store authentication tokens for this source.

        Args:
            access_token: The access token string
            refresh_token: The refresh token string (optional)
            token_type: Type of token (default: Bearer)
            expires_in: Access token lifetime in seconds
            refresh_expires_in: Refresh token lifetime in seconds
            metadata: Additional token metadata

        Returns:
            SourceAuthToken: The stored token record
        """
        from .models import SourceAuthToken

        # Calculate expiration times
        expires_at = None
        if expires_in:
            expires_at = timezone.now() + timedelta(seconds=expires_in)

        refresh_expires_at = None
        if refresh_expires_in:
            refresh_expires_at = timezone.now() + timedelta(seconds=refresh_expires_in)

        # Store or update token
        token, created = SourceAuthToken.objects.update_or_create(
            source=self.source_model,
            defaults={
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": token_type,
                "expires_at": expires_at,
                "refresh_expires_at": refresh_expires_at,
                "metadata": metadata or {},
            },
        )

        action = "Created" if created else "Updated"
        self.log_info(f"{action} auth token", expires_at=expires_at)
        return token

    def get_valid_access_token(self) -> str | None:
        """Get a valid access token, refreshing if necessary.

        Returns:
            str: Valid access token, or None if authentication failed
        """
        token = self.get_auth_token()
        if not token:
            return None

        # Check if current token is valid
        if token.is_access_token_valid() and not token.needs_refresh():
            self.log_info("Using cached valid access token")
            return token.access_token

        # Try to refresh if refresh token is available
        if token.is_refresh_token_valid():
            self.log_info("Access token expired, attempting refresh")
            if self.refresh_access_token(token):
                return token.access_token

        # Fall back to full authentication
        self.log_info("No valid tokens, performing full authentication")
        return None

    def refresh_access_token(self, token: "SourceAuthToken") -> bool:
        """Refresh an access token using the refresh token.

        This method should be overridden by sources that support token refresh.

        Args:
            token: The current token record

        Returns:
            bool: True if refresh was successful, False otherwise
        """
        self.log_info("Token refresh not implemented for this source")
        return False

    def clear_auth_token(self):
        """Clear stored authentication tokens."""
        token = self.get_auth_token()
        if token:
            token.clear_tokens()
            self.log_info("Cleared stored authentication tokens")

    def log_info(self, message: str, **kwargs):
        """Log informational message."""
        extra_info = " | ".join([f"{k}={v}" for k, v in kwargs.items()])
        full_message = f"{message} | {extra_info}" if extra_info else message
        self.logger.info(full_message)

    def log_warning(self, message: str, **kwargs):
        """Log warning message."""
        extra_info = " | ".join([f"{k}={v}" for k, v in kwargs.items()])
        full_message = f"{message} | {extra_info}" if extra_info else message
        self.logger.warning(full_message)

    def log_error(self, message: str, error: Exception | None = None, **kwargs):
        """Log error message."""
        extra_info = " | ".join([f"{k}={v}" for k, v in kwargs.items()])
        full_message = f"{message} | {extra_info}" if extra_info else message

        if error:
            full_message += f" | Error: {str(error)}"

        self.logger.error(full_message)

    def get_raw_data_path(self, variable: Variable, suffix: str = "") -> str:
        """Get file path for storing raw data."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.source_model.name}_{variable.code}_{timestamp}{suffix}"
        dir_path = f"raw_data/{self.source_model.name}"
        os.makedirs(dir_path, exist_ok=True)
        return os.path.join(dir_path, filename)

    def validate_location_match(self, location_name: str, source_name: str, context_data: dict = None) -> "Location | None":
        """Match location name to Location model using the LocationMatcher from the location app.

        This method delegates to the location app's hierarchical matching system.

        Args:
            location_name: Name of location to match
            source_name: Source identifier for gazetteer lookup
            context_data: Additional context information for improved matching

        Returns:
            Location instance if match found, None otherwise
        """
        from location.utils import location_matcher

        if not location_name or not location_name.strip():
            return None

        location_name = location_name.strip()
        context_data = context_data or {}

        # Extract and normalize admin level from context
        admin_level = self._extract_admin_level_from_context(context_data)

        # Use LocationMatcher for hierarchical matching
        location = location_matcher.match_location(location_name=location_name, source=source_name, admin_level=admin_level, context_data=context_data)

        if location:
            return location

        # No match found - record unmatched location and return None
        self._record_unmatched_location(location_name, source_name, context_data)
        return None

    def _extract_admin_level_from_context(self, context_data: dict) -> int | None:
        """Extract and normalize admin level from context data."""
        admin_level = context_data.get("expected_admin_level") or context_data.get("admin_level")

        if admin_level and str(admin_level).isdigit():
            return int(admin_level)
        return None

    def _build_context_string(self, context_data: dict) -> str:
        """Build detailed context string for unmatched location record."""
        context_parts = [f"Source: {self.source_model.name}"]

        context_fields = [
            ("original_location", "Original location"),
            ("event_name", "Event", 100),  # Truncate to 100 chars
            ("record_id", "Record ID"),
            ("additional_info", "Additional info", 100),
        ]

        for field_name, label, *max_length in context_fields:
            value = context_data.get(field_name)
            if value:
                if max_length:
                    value = str(value)[: max_length[0]]
                context_parts.append(f"{label}: {value}")

        return " | ".join(context_parts)

    def _determine_admin_level_for_record(self, location_name: str, context_data: dict) -> str:
        """Determine admin level for unmatched location record."""
        # Priority: detected_admin_level > extracted admin_level > guessed
        admin_level = (
            context_data.get("detected_admin_level") or context_data.get("expected_admin_level") or context_data.get("admin_level") or self._guess_admin_level(location_name)
        )
        return str(admin_level)

    def _record_unmatched_location(self, location_name: str, source_name: str, context_data: dict) -> None:
        """Record unmatched location for manual review."""
        from location.models import UnmatchedLocation

        self.logger.warning(f"No location match found for: {location_name}")

        try:
            context_string = self._build_context_string(context_data)
            admin_level_for_record = self._determine_admin_level_for_record(location_name, context_data)

            unmatched, created = UnmatchedLocation.objects.get_or_create(
                name=location_name,
                source=source_name,
                defaults={
                    "context": context_string,
                    "admin_level": admin_level_for_record,
                },
            )

            if not created:
                unmatched.increment_occurrence()
                self._update_admin_level_if_detected(unmatched, location_name, context_data)

            self._last_unmatched_location = unmatched

        except Exception as e:
            self.logger.error(f"Failed to record unmatched location: {str(e)}")
            self._last_unmatched_location = None

    def _update_admin_level_if_detected(self, unmatched_location, location_name: str, context_data: dict) -> None:
        """Update admin level if we have a detected one (more accurate than guessing)."""
        detected_level = context_data.get("detected_admin_level")
        if detected_level is None:
            return

        current_level = unmatched_location.admin_level
        detected_level = str(detected_level)

        if current_level != detected_level:
            unmatched_location.admin_level = detected_level
            unmatched_location.save(update_fields=["admin_level"])
            self.log_info(f"Updated admin level for unmatched location '{location_name}' from {current_level} to {detected_level}")

    def get_last_unmatched_location(self):
        """Get the last unmatched location record created during validation.

        Returns:
            UnmatchedLocation or None: The unmatched location record if location matching failed
        """
        return getattr(self, "_last_unmatched_location", None)

    def handle_unmatched_location(self, location_name: str, source_name: str, context_data: dict = None):
        """Handle location matching and create UnmatchedLocation record if no match found.

        This is a convenience method that wraps validate_location_match and returns both
        the matched location and the unmatched location record (if any).

        Args:
            location_name: Name of location to match
            source_name: Source identifier for gazetteer lookup
            context_data: Additional context information for improved matching

        Returns:
            tuple: (matched_location, unmatched_location_record)
                - matched_location: Location instance if match found, None otherwise
                - unmatched_location_record: UnmatchedLocation instance if no match, None otherwise

        Example:
            location, unmatched = self.handle_unmatched_location(
                location_name="Unknown City",
                source_name="Dataminr",
                context_data={"alert_id": "123", "criticality": "high"}
            )

            # Save data regardless of match
            VariableData.objects.create(
                variable=variable,
                gid=location,  # Can be None
                unmatched_location=unmatched,  # Can be None
                ...
            )
        """
        matched_location = self.validate_location_match(location_name, source_name, context_data)
        unmatched_location_record = self.get_last_unmatched_location() if not matched_location else None
        return matched_location, unmatched_location_record

    def _guess_admin_level(self, location_name: str) -> str:
        """Guess the admin level based on location name patterns."""
        name_lower = location_name.lower()
        if "state" in name_lower:
            return "State"
        elif "locality" in name_lower or "town" in name_lower or "city" in name_lower:
            return "Locality"
        elif "county" in name_lower or "district" in name_lower:
            return "County"
        elif "sudan" in name_lower:
            return "Country"
        return ""

    def get_last_data_date(self, variable: Variable = None) -> datetime | None:
        """Get the latest data date for incremental data fetching.

        Args:
            variable: Specific variable to check (if None, checks all source variables)

        Returns:
            datetime: The latest end_date from existing data, None if no data exists
        """
        try:
            if variable:
                # Check specific variable
                latest_data = VariableData.objects.filter(variable=variable).aggregate(models.Max("end_date"))
                latest_date = latest_data.get("end_date__max")
            else:
                # Check all variables for this source
                latest_data = VariableData.objects.filter(variable__source=self.source_model).aggregate(models.Max("end_date"))
                latest_date = latest_data.get("end_date__max")

            if latest_date:
                # Convert date to datetime for consistency
                if hasattr(latest_date, "date"):
                    # Already a datetime
                    return latest_date
                else:
                    # Convert date to datetime at start of day
                    return datetime.combine(latest_date, datetime.min.time())

            return None

        except Exception as e:
            self.log_error(f"Failed to get last data date: {str(e)}")
            return None

    def get_incremental_date_params(self, variable: Variable = None) -> dict:
        """Get date parameters for incremental data fetching.

        Args:
            variable: Specific variable to check (if None, checks all source variables)

        Returns:
            dict: Date parameters with incremental flag and start_date (None if no existing data)
        """
        try:
            last_date = self.get_last_data_date(variable)
            now = timezone.now()

            if last_date:
                # Start from day after last data point to avoid duplicates
                start_date = last_date + timedelta(days=1)
                self.log_info(f"Incremental fetch: last data at {last_date.strftime('%Y-%m-%d')}, starting from {start_date.strftime('%Y-%m-%d')}")
                return {"start_date": start_date.strftime("%Y-%m-%d"), "end_date": now.strftime("%Y-%m-%d"), "incremental": True}
            else:
                # No existing data - let the source decide what to do
                self.log_info("No existing data found")
                return {"start_date": None, "end_date": now.strftime("%Y-%m-%d"), "incremental": False}

        except Exception as e:
            self.log_error(f"Failed to get incremental date params: {str(e)}")
            return {"start_date": None, "end_date": timezone.now().strftime("%Y-%m-%d"), "incremental": False}

    # Unmatched Location Notification Methods

    def notify_unmatched_locations_summary(self, variable: Variable = None) -> None:
        """Send notification to administrators about unmatched locations found during processing.

        This method should be called after processing is complete to summarize
        any unmatched locations that were discovered during data processing.

        Args:
            variable: Specific variable that was processed (if None, checks all source variables)
        """
        try:
            # Get unmatched locations for this source from recent processing
            unmatched_locations = self._get_recent_unmatched_locations(variable)

            if not unmatched_locations:
                self.log_info("No unmatched locations found during processing")
                return

            # Send notification to administrators
            self._send_unmatched_locations_notification(unmatched_locations, variable)

        except Exception as e:
            self.log_error(f"Failed to send unmatched locations notification: {str(e)}")

    def _get_recent_unmatched_locations(self, variable: Variable = None) -> list:
        """Get unmatched locations from recent processing (last 24 hours).

        Args:
            variable: Specific variable to check (if None, checks all source variables)

        Returns:
            list: List of unmatched location records
        """
        from location.models import UnmatchedLocation

        # Get recent unmatched locations for this source
        since_time = timezone.now() - timedelta(hours=24)

        unmatched_qs = UnmatchedLocation.objects.filter(
            source=self.source_model.name,
            last_seen__gte=since_time
        ).order_by('-occurrence_count', 'name')

        return list(unmatched_qs[:50])  # Limit to top 50 most frequent

    def _send_unmatched_locations_notification(self, unmatched_locations: list, variable: Variable = None) -> None:
        """Send notification to administrators about unmatched locations.

        Args:
            unmatched_locations: List of UnmatchedLocation objects
            variable: Variable that was processed (optional)
        """
        try:
            from notifications.models import InternalNotification

            # Get all administrators (superusers)
            administrators = User.objects.filter(is_superuser=True, is_active=True)

            if not administrators.exists():
                self.log_error("No administrators found to notify about unmatched locations")
                return

            # Create notification content
            title = self._build_notification_title(len(unmatched_locations), variable)
            message = self._build_notification_message(unmatched_locations, variable)
            action_url = self._build_notification_action_url()

            # Send notification to each administrator
            notifications_created = 0
            for admin in administrators:
                # Check if user should receive system notifications
                if hasattr(admin, 'notification_preferences'):
                    if not admin.notification_preferences.should_receive_notification('system'):
                        continue

                notification = InternalNotification.objects.create(
                    user=admin,
                    type='system',
                    priority='normal',
                    title=title,
                    message=message,
                    action_url=action_url,
                    action_text="Manage Unmatched Locations"
                )
                notifications_created += 1

            self.log_info(f"Sent unmatched locations notification to {notifications_created} administrators")

        except Exception as e:
            self.log_error(f"Failed to send notification to administrators: {str(e)}")

    def _build_notification_title(self, count: int, variable: Variable = None) -> str:
        """Build notification title for unmatched locations.

        Args:
            count: Number of unmatched locations
            variable: Variable that was processed (optional)

        Returns:
            str: Notification title
        """
        source_name = self.source_model.name
        if variable:
            return f"Unmatched Locations: {count} found during {source_name} - {variable.name} processing"
        else:
            return f"Unmatched Locations: {count} found during {source_name} processing"

    def _build_notification_message(self, unmatched_locations: list, variable: Variable = None) -> str:
        """Build notification message content for unmatched locations.

        Args:
            unmatched_locations: List of UnmatchedLocation objects
            variable: Variable that was processed (optional)

        Returns:
            str: Notification message content
        """
        source_name = self.source_model.name

        # Build base message
        if variable:
            message = f"During processing of {source_name} - {variable.name}, {len(unmatched_locations)} unmatched locations were found.\n\n"
        else:
            message = f"During processing of {source_name}, {len(unmatched_locations)} unmatched locations were found.\n\n"

        # Add summary of most frequent unmatched locations
        message += "Most frequent unmatched locations:\n"
        for location in unmatched_locations[:10]:  # Top 10
            message += f"• {location.name} ({location.occurrence_count} occurrences)\n"

        if len(unmatched_locations) > 10:
            message += f"... and {len(unmatched_locations) - 10} more\n"

        message += "\nThese locations could not be matched to existing administrative boundaries and may need manual review or gazetteer updates."

        return message

    def _build_notification_action_url(self) -> str:
        """Build URL for notification action button.

        Returns:
            str: URL to unmatched locations management page
        """
        try:
            return reverse('location:unmatched_locations')
        except:
            # Fallback to admin interface if location app URL not available
            return reverse('admin:location_unmatchedlocation_changelist')

    def _get_administrators(self) -> models.QuerySet:
        """Get list of administrator users who should receive notifications.

        Returns:
            QuerySet: Administrator users
        """
        return User.objects.filter(
            is_superuser=True,
            is_active=True
        ).select_related('notification_preferences')

    # Individual Source Testing Methods

    def test_connectivity(self) -> dict[str, Any]:
        """Test basic API connectivity without authentication.

        Default implementation tests base_url if available.
        Override in source classes for custom connectivity logic.

        Returns:
            dict: Connectivity test results with status, timing, and details
        """
        try:
            import time

            import requests

            if not hasattr(self.source_model, 'base_url') or not self.source_model.base_url:
                return {"status": "skipped", "reason": "No base_url configured"}

            start_time = time.time()
            response = requests.get(self.source_model.base_url, timeout=10)
            response_time_ms = (time.time() - start_time) * 1000

            return {
                "status": "success" if response.status_code < 400 else "failed",
                "status_code": response.status_code,
                "response_time_ms": round(response_time_ms, 2),
                "url_tested": self.source_model.base_url
            }
        except Exception as e:
            return {
                "status": "failed",
                "error": str(e),
                "url_tested": getattr(self.source_model, 'base_url', 'No URL configured')
            }

    def test_authentication(self) -> dict[str, Any]:
        """Test authentication with provided credentials.

        Default implementation checks required environment variables.
        Override in source classes for actual authentication testing.

        Returns:
            dict: Authentication test results with status and details
        """
        required_vars = self.get_required_env_vars()

        if not required_vars:
            return {
                "status": "success",
                "message": "No credentials required",
                "credentials_required": False
            }

        missing_vars = [var for var in required_vars if not os.getenv(var)]

        if missing_vars:
            return {
                "status": "failed",
                "error": f"Missing environment variables: {', '.join(missing_vars)}",
                "missing_vars": missing_vars,
                "required_vars": required_vars,
                "credentials_required": True
            }

        return {
            "status": "success",
            "message": "Required credentials present",
            "credentials_required": True,
            "configured_vars": required_vars
        }

    def get_required_env_vars(self) -> list[str]:
        """Return list of required environment variables for this source.

        Override in source classes to specify their requirements.

        Returns:
            list[str]: List of required environment variable names
        """
        return []

    def test_data_retrieval(self, **kwargs) -> dict[str, Any]:
        """Test minimal data retrieval.

        Default implementation calls get() with test parameters.
        Override for source-specific testing logic.

        Args:
            **kwargs: Additional parameters for testing

        Returns:
            dict: Data retrieval test results
        """
        try:
            # Get a test variable for this source
            test_variable = self.source_model.variables.first()
            if not test_variable:
                return {
                    "status": "failed",
                    "error": "No variables configured for source",
                    "variables_count": 0
                }

            # Try minimal data retrieval
            test_params = self.get_test_parameters()
            test_params.update(kwargs)

            self.log_info(f"Testing data retrieval with parameters: {test_params}")
            success = self.get(test_variable, **test_params)

            return {
                "status": "success" if success else "failed",
                "variable_tested": test_variable.code,
                "test_parameters": test_params,
                "variables_count": self.source_model.variables.count()
            }
        except Exception as e:
            return {
                "status": "failed",
                "error": str(e),
                "test_parameters": getattr(self, '_last_test_params', {})
            }

    def get_test_parameters(self) -> dict:
        """Return minimal parameters for testing data retrieval.

        Override in source classes to provide source-specific test parameters.

        Returns:
            dict: Test parameters for stable data retrieval
        """
        return {}

    def run_all_connectivity_tests(self) -> dict[str, Any]:
        """Run all connectivity tests and return comprehensive results.

        Returns:
            dict: Complete test results for connectivity, authentication, and data retrieval
        """
        results = {
            "source_name": self.source_model.name,
            "source_class": self.source_model.class_name,
            "test_timestamp": timezone.now().isoformat(),
            "tests": {}
        }

        # Test connectivity
        self.log_info("Running connectivity test")
        connectivity_result = self.test_connectivity()
        results["tests"]["connectivity"] = connectivity_result

        # Test authentication
        self.log_info("Running authentication test")
        auth_result = self.test_authentication()
        results["tests"]["authentication"] = auth_result

        # Test data retrieval only if connectivity and auth passed
        if (connectivity_result["status"] == "success" and
            auth_result["status"] == "success"):
            self.log_info("Running data retrieval test")
            retrieval_result = self.test_data_retrieval()
            results["tests"]["data_retrieval"] = retrieval_result
        else:
            results["tests"]["data_retrieval"] = {
                "status": "skipped",
                "reason": "Connectivity or authentication failed"
            }

        # Calculate overall status
        test_statuses = [test["status"] for test in results["tests"].values()]
        if "failed" in test_statuses:
            overall_status = "failed"
        elif "skipped" in test_statuses:
            overall_status = "partial"
        else:
            overall_status = "success"

        results["overall_status"] = overall_status
        results["summary"] = self._generate_test_summary(results["tests"])

        return results

    def _generate_test_summary(self, test_results: dict) -> str:
        """Generate human-readable summary of test results."""
        connectivity = test_results.get("connectivity", {})
        authentication = test_results.get("authentication", {})
        data_retrieval = test_results.get("data_retrieval", {})

        parts = []

        # Connectivity summary
        if connectivity["status"] == "success":
            response_time = connectivity.get("response_time_ms", 0)
            parts.append(f"API accessible ({response_time}ms)")
        elif connectivity["status"] == "failed":
            parts.append("API inaccessible")

        # Authentication summary
        if authentication["status"] == "success":
            if authentication.get("credentials_required", False):
                parts.append("credentials valid")
            else:
                parts.append("no credentials required")
        elif authentication["status"] == "failed":
            missing = authentication.get("missing_vars", [])
            if missing:
                parts.append(f"missing: {', '.join(missing)}")
            else:
                parts.append("authentication failed")

        # Data retrieval summary
        if data_retrieval["status"] == "success":
            parts.append("data retrieval OK")
        elif data_retrieval["status"] == "failed":
            parts.append("data retrieval failed")

        return ", ".join(parts) if parts else "No test results"
