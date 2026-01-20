"""Serializers for alerts app API responses."""

from typing import Dict, List, Optional

from django.contrib.auth.models import User

from .models import Alert, ShockType, UserAlert


class AlertSerializer:
    """Base serializer for Alert objects."""

    @staticmethod
    def serialize_shock_type(shock_type: ShockType, include_display_info: bool = False) -> Dict:
        """Serialize shock type data."""
        data = {
            "id": shock_type.id,
            "name": shock_type.name,
        }

        if include_display_info:
            data.update({
                "icon": shock_type.icon,
                "color": shock_type.color,
                "css_class": shock_type.css_class,
            })

        return data

    @staticmethod
    def serialize_data_source(data_source, include_info_url: bool = False) -> Dict:
        """Serialize data source data."""
        data = {
            "id": data_source.id,
            "name": data_source.name,
        }

        if include_info_url and hasattr(data_source, 'info_url'):
            data["info_url"] = data_source.info_url

        return data

    @staticmethod
    def serialize_location(location, include_admin_level: bool = False) -> Dict:
        """Serialize location data."""
        data = {
            "id": location.id,
            "name": location.name,
            "geo_id": location.geo_id,
            "point": {
                "coordinates": [location.point.x, location.point.y] if location.point else None
            } if location.point else None,
        }

        if include_admin_level and location.admin_level:
            data["admin_level"] = {
                "code": location.admin_level.code,
                "name": location.admin_level.name
            }

        return data

    @staticmethod
    def serialize_user_interaction(user_alert: Optional[UserAlert], include_timestamps: bool = False) -> Optional[Dict]:
        """Serialize user interaction data."""
        if not user_alert:
            return None

        data = {
            "is_read": user_alert.is_read,
            "is_bookmarked": user_alert.bookmarked,
            "rating": user_alert.rating,
            "is_flagged": user_alert.is_flagged,
        }

        if include_timestamps:
            data.update({
                "received_at": user_alert.received_at.isoformat() if user_alert.received_at else None,
                "read_at": user_alert.read_at.isoformat() if user_alert.read_at else None,
                "rating_at": user_alert.rating_at.isoformat() if user_alert.rating_at else None,
                "flag_false": user_alert.flag_false,
                "flag_incomplete": user_alert.flag_incomplete,
                "comment": user_alert.comment,
            })

        return data

    def serialize_basic(self, alert: Alert, user_alert: Optional[UserAlert] = None,
                       include_display_info: bool = False) -> Dict:
        """Serialize basic alert data for list views."""
        return {
            "id": alert.id,
            "title": alert.title,
            "text": alert.text,
            "shock_date": alert.shock_date.isoformat(),
            "severity": alert.severity,
            "severity_display": alert.severity_display,
            "valid_from": alert.valid_from.isoformat(),
            "valid_until": alert.valid_until.isoformat(),
            "is_active": alert.is_active,
            "shock_type": self.serialize_shock_type(alert.shock_type, include_display_info),
            "data_source": self.serialize_data_source(alert.data_source),
            "locations": [
                self.serialize_location(location) for location in alert.locations.all()
            ],
            "user_interaction": self.serialize_user_interaction(user_alert),
        }


class AlertDetailSerializer(AlertSerializer):
    """Extended serializer for detailed alert views."""

    def serialize_detailed(self, alert: Alert, user_alert: Optional[UserAlert] = None) -> Dict:
        """Serialize detailed alert data for detail views."""
        data = self.serialize_basic(alert, user_alert, include_display_info=False)

        # Add detailed fields
        data.update({
            "created_at": alert.created_at.isoformat(),
            "updated_at": alert.updated_at.isoformat(),
            "data_source": self.serialize_data_source(alert.data_source, include_info_url=True),
            "locations": [
                self.serialize_location(location, include_admin_level=True)
                for location in alert.locations.all()
            ],
            "user_interaction": self.serialize_user_interaction(user_alert, include_timestamps=True),
        })

        return data


class PublicAlertSerializer(AlertSerializer):
    """Serializer for public API endpoints."""

    def serialize_public(self, alert: Alert, include_community_stats: bool = False) -> Dict:
        """Serialize alert data for public API."""
        data = self.serialize_basic(alert, user_alert=None, include_display_info=True)

        # Add public-specific fields
        data.update({
            "created_at": alert.created_at.isoformat(),
            "updated_at": alert.updated_at.isoformat(),
            "locations": [
                self.serialize_location(location, include_admin_level=True)
                for location in alert.locations.all()
            ],
        })

        # Remove user interaction data for public API
        data.pop("user_interaction", None)

        if include_community_stats:
            data["community_stats"] = {
                "average_rating": alert.average_rating,
                "rating_count": alert.rating_count,
                "is_flagged_false": alert.is_flagged_false,
                "is_flagged_incomplete": alert.is_flagged_incomplete,
                "false_flag_count": alert.false_flag_count,
                "incomplete_flag_count": alert.incomplete_flag_count,
            }

        return data


class ShockTypeSerializer:
    """Serializer for ShockType objects."""

    @staticmethod
    def serialize_basic(shock_type: ShockType, include_stats: bool = False) -> Dict:
        """Serialize shock type data."""
        data = {
            "id": shock_type.id,
            "name": shock_type.name,
            "icon": shock_type.icon,
            "color": shock_type.color,
            "css_class": shock_type.css_class,
            "background_css_class": shock_type.background_css_class,
        }

        if include_stats:
            # These would be pre-calculated using annotations
            if hasattr(shock_type, 'alert_count'):
                data["alert_count"] = shock_type.alert_count
            if hasattr(shock_type, 'active_alert_count'):
                data["active_alert_count"] = shock_type.active_alert_count
            if hasattr(shock_type, 'created_at'):
                data.update({
                    "created_at": shock_type.created_at.isoformat(),
                    "updated_at": shock_type.updated_at.isoformat(),
                })

        return data


class SubscriptionSerializer:
    """Serializer for Subscription objects."""

    @staticmethod
    def serialize_basic(subscription) -> Dict:
        """Serialize subscription data."""
        return {
            "id": subscription.id,
            "active": subscription.active,
            "method": subscription.method,
            "frequency": subscription.frequency,
            "created_at": subscription.created_at.isoformat(),
            "updated_at": subscription.updated_at.isoformat(),
            "locations": [
                {"id": location.id, "name": location.name, "geo_id": location.geo_id}
                for location in subscription.locations.all()
            ],
            "shock_types": [
                {"id": shock_type.id, "name": shock_type.name}
                for shock_type in subscription.shock_types.all()
            ],
        }


class ResponseSerializer:
    """Helper for API response formatting."""

    @staticmethod
    def success_response(data: Dict, message: str = "Success") -> Dict:
        """Create standardized success response."""
        return {
            "success": True,
            "message": message,
            **data
        }

    @staticmethod
    def error_response(error: str, details: Optional[Dict] = None) -> Dict:
        """Create standardized error response."""
        response = {
            "success": False,
            "error": error
        }
        if details:
            response["details"] = details
        return response

    @staticmethod
    def paginated_response(data: List, page: int, total: int, pages: int,
                          has_next: bool, has_previous: bool) -> Dict:
        """Create standardized paginated response."""
        return {
            "success": True,
            "count": len(data),
            "total": total,
            "page": page,
            "pages": pages,
            "has_next": has_next,
            "has_previous": has_previous,
            "results": data,
        }