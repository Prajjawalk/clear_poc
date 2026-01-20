"""API views for alerts app."""

import json
from datetime import datetime, timedelta

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Prefetch, Q
from django.http import JsonResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .cache import AlertCacheManager
from .models import Alert, ShockType, Subscription, UserAlert
from .serializers import AlertDetailSerializer, AlertSerializer, PublicAlertSerializer, ShockTypeSerializer, SubscriptionSerializer


@method_decorator(login_required, name="dispatch")
class AlertsAPIView(View):
    """API endpoint for alerts data."""

    def get(self, request):
        """Get filtered alerts data for map and other views."""
        # Base queryset - only approved alerts
        queryset = Alert.objects.filter(go_no_go=True).select_related("shock_type", "data_source").prefetch_related("locations")

        # Apply filters
        shock_type = request.GET.get("shock_type")
        if shock_type:
            queryset = queryset.filter(shock_type_id=shock_type)

        severity = request.GET.get("severity")
        if severity:
            queryset = queryset.filter(severity=severity)

        date_from = request.GET.get("date_from")
        if date_from:
            queryset = queryset.filter(shock_date__gte=date_from)

        date_to = request.GET.get("date_to")
        if date_to:
            queryset = queryset.filter(shock_date__lte=date_to)

        search = request.GET.get("search")
        if search:
            queryset = queryset.filter(Q(title__icontains=search) | Q(text__icontains=search))

        # Add prefetch for user interactions to avoid N+1 queries
        user_alerts_prefetch = Prefetch("useralert_set", queryset=UserAlert.objects.filter(user=request.user), to_attr="user_interactions")
        queryset = queryset.prefetch_related(user_alerts_prefetch)

        # Limit results for performance
        limit = min(int(request.GET.get("limit", 100)), 1000)
        queryset = queryset.order_by("-shock_date", "-created_at")[:limit]

        # Convert to JSON format using serializer
        serializer = AlertSerializer()
        alerts_data = []
        for alert in queryset:
            # Get user interaction data - now using prefetched data
            user_alert = None
            if hasattr(alert, "user_interactions") and alert.user_interactions:
                user_alert = alert.user_interactions[0]

            alert_data = serializer.serialize_basic(alert, user_alert)
            alerts_data.append(alert_data)

        return JsonResponse(
            {
                "success": True,
                "count": len(alerts_data),
                "alerts": alerts_data,
                "filters": {"shock_type": shock_type, "severity": severity, "date_from": date_from, "date_to": date_to, "search": search},
            }
        )


@method_decorator(login_required, name="dispatch")
class AlertDetailAPIView(View):
    """API endpoint for individual alert details."""

    def get(self, request, alert_id):
        """Get detailed alert data."""
        try:
            alert = Alert.objects.select_related("shock_type", "data_source").prefetch_related("locations").get(id=alert_id, go_no_go=True)
        except Alert.DoesNotExist:
            return JsonResponse({"success": False, "error": "Alert not found"}, status=404)

        # Get user interaction data
        user_alert = None
        try:
            user_alert = UserAlert.objects.get(user=request.user, alert=alert)
        except UserAlert.DoesNotExist:
            pass

        # Use serializer for detailed alert data
        serializer = AlertDetailSerializer()
        alert_data = serializer.serialize_detailed(alert, user_alert)

        return JsonResponse({"success": True, "alert": alert_data})


@method_decorator(login_required, name="dispatch")
class ShockTypesAPIView(View):
    """API endpoint for shock types."""

    def get(self, request):
        """Get all shock types."""
        # Try to get from cache first
        cached_data = AlertCacheManager.get_cached_shock_types(include_stats=True)
        if cached_data:
            return JsonResponse({"success": True, "shock_types": cached_data})

        # Use annotation to avoid N+1 queries for alert count
        shock_types = ShockType.objects.annotate(alert_count=Count("alert", filter=Q(alert__go_no_go=True))).order_by("name")

        serializer = ShockTypeSerializer()
        shock_types_data = [serializer.serialize_basic(shock_type, include_stats=True) for shock_type in shock_types]

        # Cache the results
        AlertCacheManager.cache_shock_types(shock_types_data, include_stats=True)

        return JsonResponse({"success": True, "shock_types": shock_types_data})


@method_decorator(login_required, name="dispatch")
class UserSubscriptionsAPIView(View):
    """API endpoint for user subscriptions."""

    def get(self, request):
        """Get user subscriptions."""
        subscriptions = Subscription.objects.filter(user=request.user).prefetch_related("locations", "shock_types").order_by("-created_at")

        serializer = SubscriptionSerializer()
        subscriptions_data = [serializer.serialize_basic(subscription) for subscription in subscriptions]

        return JsonResponse({"success": True, "subscriptions": subscriptions_data})


@method_decorator(login_required, name="dispatch")
class AlertStatsAPIView(View):
    """API endpoint for alert statistics."""

    def get(self, request):
        """Get alert statistics."""
        # Try to get from cache first
        cached_stats = AlertCacheManager.get_cached_stats(request.user.id)
        if cached_stats:
            return JsonResponse(cached_stats)

        # Note: Count, timezone, timedelta are already imported at top of file
        now = timezone.now()
        last_30_days = now - timedelta(days=30)
        last_7_days = now - timedelta(days=7)

        # Base queryset
        base_queryset = Alert.objects.filter(go_no_go=True)

        # Overall stats
        total_alerts = base_queryset.count()
        active_alerts = base_queryset.filter(valid_from__lte=now, valid_until__gte=now).count()

        # Recent activity
        recent_30_days = base_queryset.filter(created_at__gte=last_30_days).count()
        recent_7_days = base_queryset.filter(created_at__gte=last_7_days).count()

        # By shock type
        by_shock_type = list(base_queryset.values("shock_type__name").annotate(count=Count("id")).order_by("-count"))

        # By severity
        by_severity = list(base_queryset.values("severity").annotate(count=Count("id")).order_by("severity"))

        # User-specific stats
        user_bookmarks = UserAlert.objects.filter(user=request.user, bookmarked=True).count()

        user_ratings = UserAlert.objects.filter(user=request.user, rating__isnull=False).count()

        user_subscriptions = Subscription.objects.filter(user=request.user, active=True).count()

        stats_data = {
            "success": True,
            "stats": {
                "overview": {"total_alerts": total_alerts, "active_alerts": active_alerts, "recent_30_days": recent_30_days, "recent_7_days": recent_7_days},
                "by_shock_type": by_shock_type,
                "by_severity": by_severity,
                "user": {"bookmarks": user_bookmarks, "ratings": user_ratings, "subscriptions": user_subscriptions},
            },
        }

        # Cache the results
        AlertCacheManager.cache_stats(stats_data, request.user.id)

        return JsonResponse(stats_data)


# External Integration APIs (for third-party systems)


class PublicAlertsAPIView(View):
    """Public API endpoint for alerts data (for external integrations)."""

    def get(self, request):
        """Get public alerts data without user-specific information."""
        # Base queryset - only approved alerts
        queryset = Alert.objects.filter(go_no_go=True).select_related("shock_type", "data_source").prefetch_related("locations")

        # Apply filters
        shock_type = request.GET.get("shock_type")
        if shock_type:
            queryset = queryset.filter(shock_type_id=shock_type)

        severity = request.GET.get("severity")
        if severity:
            try:
                severity = int(severity)
                queryset = queryset.filter(severity=severity)
            except ValueError:
                pass

        # Active only filter (default: true for external APIs)
        active_only = request.GET.get("active_only", "true").lower() == "true"
        if active_only:
            now = timezone.now()
            queryset = queryset.filter(valid_from__lte=now, valid_until__gte=now)

        # Date range filters
        date_from = request.GET.get("date_from")
        if date_from:
            try:
                date_from = datetime.fromisoformat(date_from.replace("Z", "+00:00"))
                queryset = queryset.filter(shock_date__gte=date_from)
            except ValueError:
                pass

        date_to = request.GET.get("date_to")
        if date_to:
            try:
                date_to = datetime.fromisoformat(date_to.replace("Z", "+00:00"))
                queryset = queryset.filter(shock_date__lte=date_to)
            except ValueError:
                pass

        # Location filter
        location_ids = request.GET.get("location_ids")
        if location_ids:
            try:
                location_list = [int(x.strip()) for x in location_ids.split(",")]
                queryset = queryset.filter(locations__id__in=location_list)
            except ValueError:
                pass

        # Search filter
        search = request.GET.get("search")
        if search:
            queryset = queryset.filter(Q(title__icontains=search) | Q(text__icontains=search))

        # Pagination
        page = int(request.GET.get("page", 1))
        page_size = min(int(request.GET.get("page_size", 50)), 100)  # Max 100 items per page

        queryset = queryset.order_by("-shock_date", "-created_at")
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)

        # Convert to JSON format using serializer
        serializer = PublicAlertSerializer()
        alerts_data = []
        for alert in page_obj:
            alert_data = serializer.serialize_public(alert, include_community_stats=True)
            alerts_data.append(alert_data)

        return JsonResponse(
            {
                "success": True,
                "count": len(alerts_data),
                "total": paginator.count,
                "page": page,
                "pages": paginator.num_pages,
                "has_next": page_obj.has_next(),
                "has_previous": page_obj.has_previous(),
                "alerts": alerts_data,
                "filters_applied": {
                    "shock_type": shock_type,
                    "severity": severity,
                    "active_only": active_only,
                    "date_from": date_from.isoformat() if date_from else None,
                    "date_to": date_to.isoformat() if date_to else None,
                    "location_ids": location_ids,
                    "search": search,
                },
            }
        )


class PublicShockTypesAPIView(View):
    """Public API endpoint for shock types."""

    def get(self, request):
        """Get all shock types with alert counts."""
        shock_types = ShockType.objects.annotate(
            alert_count=Count("alert", filter=Q(alert__go_no_go=True)),
            active_alert_count=Count("alert", filter=Q(alert__go_no_go=True, alert__valid_from__lte=timezone.now(), alert__valid_until__gte=timezone.now())),
        ).order_by("name")

        shock_types_data = [
            {
                "id": shock_type.id,
                "name": shock_type.name,
                "icon": shock_type.icon,
                "color": shock_type.color,
                "css_class": shock_type.css_class,
                "background_css_class": shock_type.background_css_class,
                "alert_count": shock_type.alert_count,
                "active_alert_count": shock_type.active_alert_count,
                "created_at": shock_type.created_at.isoformat(),
                "updated_at": shock_type.updated_at.isoformat(),
            }
            for shock_type in shock_types
        ]

        return JsonResponse({"success": True, "count": len(shock_types_data), "shock_types": shock_types_data})


class PublicAlertStatsAPIView(View):
    """Public API endpoint for alert statistics."""

    def get(self, request):
        """Get comprehensive alert statistics for external integrations."""
        now = timezone.now()
        last_30_days = now - timedelta(days=30)
        last_7_days = now - timedelta(days=7)
        last_24_hours = now - timedelta(hours=24)

        # Base queryset
        base_queryset = Alert.objects.filter(go_no_go=True)

        # Overall stats
        total_alerts = base_queryset.count()
        active_alerts = base_queryset.filter(valid_from__lte=now, valid_until__gte=now).count()

        # Time-based stats
        recent_30_days = base_queryset.filter(created_at__gte=last_30_days).count()
        recent_7_days = base_queryset.filter(created_at__gte=last_7_days).count()
        recent_24_hours = base_queryset.filter(created_at__gte=last_24_hours).count()

        # By shock type (with active alerts)
        by_shock_type = list(
            base_queryset.values("shock_type__id", "shock_type__name", "shock_type__icon", "shock_type__color")
            .annotate(total_count=Count("id"), active_count=Count("id", filter=Q(valid_from__lte=now, valid_until__gte=now)))
            .order_by("-total_count")
        )

        # By severity
        by_severity = list(
            base_queryset.values("severity").annotate(total_count=Count("id"), active_count=Count("id", filter=Q(valid_from__lte=now, valid_until__gte=now))).order_by("severity")
        )

        # Add severity display names
        severity_choices = dict(Alert.SEVERITY_CHOICES)
        for item in by_severity:
            item["severity_display"] = severity_choices.get(item["severity"], "Unknown")

        # Top locations by alert count
        top_locations = list(base_queryset.values("locations__id", "locations__name", "locations__geo_id").annotate(alert_count=Count("id")).order_by("-alert_count")[:10])

        # Community engagement stats
        community_stats = {
            "total_ratings": UserAlert.objects.filter(rating__isnull=False).count(),
            "average_rating": UserAlert.objects.filter(rating__isnull=False).aggregate(avg_rating=Avg("rating"))["avg_rating"],
            "total_bookmarks": UserAlert.objects.filter(bookmarked=True).count(),
            "false_flags": UserAlert.objects.filter(flag_false=True).count(),
            "incomplete_flags": UserAlert.objects.filter(flag_incomplete=True).count(),
            "comments": UserAlert.objects.filter(comment__isnull=False, comment__gt="").count(),
        }

        return JsonResponse(
            {
                "success": True,
                "generated_at": now.isoformat(),
                "stats": {
                    "overview": {
                        "total_alerts": total_alerts,
                        "active_alerts": active_alerts,
                        "recent_30_days": recent_30_days,
                        "recent_7_days": recent_7_days,
                        "recent_24_hours": recent_24_hours,
                    },
                    "by_shock_type": by_shock_type,
                    "by_severity": by_severity,
                    "top_locations": top_locations,
                    "community_engagement": community_stats,
                },
            }
        )


@csrf_exempt
@require_http_methods(["POST"])
def webhook_alert_create(request):
    """Webhook endpoint for external systems to create alerts."""
    try:
        data = json.loads(request.body)

        # Basic validation
        required_fields = ["title", "text", "shock_type_id", "data_source_id", "shock_date", "severity"]
        for field in required_fields:
            if field not in data:
                return JsonResponse({"success": False, "error": f"Missing required field: {field}"}, status=400)

        # Validate shock_date format
        try:
            shock_date = datetime.fromisoformat(data["shock_date"].replace("Z", "+00:00")).date()
        except (ValueError, AttributeError):
            return JsonResponse({"success": False, "error": "Invalid shock_date format. Use ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)"}, status=400)

        # Validate severity
        try:
            severity = int(data["severity"])
            if severity < 1 or severity > 5:
                raise ValueError()
        except (ValueError, TypeError):
            return JsonResponse({"success": False, "error": "Severity must be an integer between 1 and 5"}, status=400)

        # Set default validity period if not provided
        if "valid_from" not in data:
            data["valid_from"] = timezone.now()
        else:
            try:
                data["valid_from"] = datetime.fromisoformat(data["valid_from"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                return JsonResponse({"success": False, "error": "Invalid valid_from format. Use ISO format"}, status=400)

        if "valid_until" not in data:
            data["valid_until"] = data["valid_from"] + timedelta(days=7)  # Default 7 days
        else:
            try:
                data["valid_until"] = datetime.fromisoformat(data["valid_until"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                return JsonResponse({"success": False, "error": "Invalid valid_until format. Use ISO format"}, status=400)

        # Validate foreign key relationships
        try:
            shock_type = ShockType.objects.get(id=data["shock_type_id"])
        except ShockType.DoesNotExist:
            return JsonResponse({"success": False, "error": f"Shock type with ID {data['shock_type_id']} not found"}, status=400)

        from data_pipeline.models import Source

        try:
            data_source = Source.objects.get(id=data["data_source_id"])
        except Source.DoesNotExist:
            return JsonResponse({"success": False, "error": f"Data source with ID {data['data_source_id']} not found"}, status=400)

        # Create the alert
        alert = Alert.objects.create(
            title=data["title"][:255],  # Truncate to max length
            text=data["text"],
            shock_type=shock_type,
            data_source=data_source,
            shock_date=shock_date,
            severity=severity,
            valid_from=data["valid_from"],
            valid_until=data["valid_until"],
            go_no_go=data.get("go_no_go", False),  # Default to False for external alerts
        )

        # Add locations if provided
        if "location_ids" in data:
            from location.models import Location

            try:
                location_ids = data["location_ids"] if isinstance(data["location_ids"], list) else [data["location_ids"]]
                locations = Location.objects.filter(id__in=location_ids)
                alert.locations.set(locations)
            except (ValueError, TypeError):
                pass  # Skip invalid location IDs

        return JsonResponse(
            {
                "success": True,
                "message": "Alert created successfully",
                "alert": {
                    "id": alert.id,
                    "title": alert.title,
                    "shock_date": alert.shock_date.isoformat(),
                    "severity": alert.severity,
                    "go_no_go": alert.go_no_go,
                    "created_at": alert.created_at.isoformat(),
                },
            },
            status=201,
        )

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON payload"}, status=400)
    except Exception as e:
        return JsonResponse({"success": False, "error": f"Internal server error: {str(e)}"}, status=500)
