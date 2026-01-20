"""REST API endpoints for alert framework."""

from datetime import timedelta

from django.db.models import Count, Q
from django.http import JsonResponse
from django.utils import timezone
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.views.generic import ListView

from .models import AlertTemplate, Detection, Detector
from .serializers import (
    DetectionSerializer,
    DetectorSerializer,
    PaginationSerializer,
)
from .tasks import run_detector
from .utils import build_detection_filters


class DetectorListAPIView(ListView):
    """API endpoint for listing detectors with pagination and filtering."""

    model = Detector
    paginate_by = 20

    def get_queryset(self):
        """Filter detectors based on query parameters."""
        # Optimize with specific select_related for schedule FK and prefetch for detections
        queryset = Detector.objects.select_related().prefetch_related("detections__shock_type", "detections__locations")

        # Filter by active status
        if self.request.GET.get("active"):
            active = self.request.GET.get("active").lower() == "true"
            queryset = queryset.filter(active=active)

        # Search by name or description
        search = self.request.GET.get("search")
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(description__icontains=search))

        return queryset.order_by("-created_at")

    def get(self, request, *args, **kwargs):
        """Return JSON response with detector list."""
        queryset = self.get_queryset()
        paginator = self.get_paginator(queryset, self.paginate_by)
        page_number = request.GET.get("page")
        page_obj = paginator.get_page(page_number)

        detectors = [DetectorSerializer.to_dict(detector, include_stats=True) for detector in page_obj]

        return JsonResponse(
            {
                "detectors": detectors,
                "pagination": PaginationSerializer.to_dict(page_obj, paginator),
            }
        )


class DetectorDetailAPIView(View):
    """API endpoint for detector details and configuration."""

    def get(self, request, detector_id):
        """Get detector details with statistics."""
        try:
            detector = Detector.objects.select_related().prefetch_related("detections__shock_type", "detections__locations__admin_level").get(id=detector_id)
        except Detector.DoesNotExist:
            return JsonResponse({"error": "Detector not found"}, status=404)

        # Get detector with statistics
        detector_data = DetectorSerializer.to_dict(detector, include_stats=True)

        # Add recent detections
        recent_detections = detector.detections.filter(detection_timestamp__gte=timezone.now() - timedelta(days=30)).order_by("-detection_timestamp")[:10]

        detector_data["recent_detections"] = [DetectionSerializer.to_summary_dict(detection) for detection in recent_detections]

        return JsonResponse(detector_data)


class DetectionListAPIView(ListView):
    """API endpoint for listing detections with advanced filtering."""

    model = Detection
    paginate_by = 50

    def get_queryset(self):
        """Filter detections based on query parameters."""
        # Optimize with specific select_related and prefetch_related
        queryset = Detection.objects.select_related("detector", "shock_type", "duplicate_of", "duplicate_of__detector").prefetch_related("locations__admin_level", "duplicates")

        # Apply filters using utility function
        filters = build_detection_filters(self.request.GET)
        if filters:
            queryset = queryset.filter(**filters)

        return queryset.order_by("-detection_timestamp")

    def get(self, request, *args, **kwargs):
        """Return JSON response with detection list."""
        queryset = self.get_queryset()
        paginator = self.get_paginator(queryset, self.paginate_by)
        page_number = request.GET.get("page")
        page_obj = paginator.get_page(page_number)

        detections = [DetectionSerializer.to_dict(detection) for detection in page_obj]

        return JsonResponse(
            {
                "detections": detections,
                "pagination": PaginationSerializer.to_dict(page_obj, paginator),
            }
        )


class DetectionDetailAPIView(View):
    """API endpoint for individual detection details."""

    def get(self, request, detection_id):
        """Get detection details with full metadata."""
        try:
            detection = (
                Detection.objects.select_related("detector", "shock_type", "duplicate_of__detector")
                .prefetch_related("locations__admin_level", "duplicates__detector")
                .get(id=detection_id)
            )
        except Detection.DoesNotExist:
            return JsonResponse({"error": "Detection not found"}, status=404)

        return JsonResponse(
            {
                "id": detection.id,
                "title": detection.title,
                "detector": {
                    "id": detection.detector.id,
                    "name": detection.detector.name,
                    "description": detection.detector.description,
                },
                "detection_timestamp": detection.detection_timestamp.isoformat(),
                "status": detection.status,
                "confidence_score": detection.confidence_score,
                "created_at": detection.created_at.isoformat(),
                "processed_at": detection.processed_at.isoformat() if detection.processed_at else None,
                "locations": [
                    {
                        "id": location.id,
                        "name": location.name,
                        "name_ar": location.name_ar if hasattr(location, "name_ar") else None,
                        "admin_level": {
                            "id": location.admin_level.id,
                            "name": location.admin_level.name,
                            "code": location.admin_level.code,
                        }
                        if location.admin_level
                        else None,
                        "coordinates": {
                            "latitude": location.latitude,
                            "longitude": location.longitude,
                        }
                        if location.latitude and location.longitude
                        else None,
                    }
                    for location in detection.locations.all()
                ],
                "detection_data": detection.detection_data,
            }
        )


@csrf_exempt
@require_http_methods(["POST"])
def run_detector_api(request, detector_id):
    """API endpoint to manually trigger detector execution."""
    try:
        detector = Detector.objects.get(id=detector_id)
    except Detector.DoesNotExist:
        return JsonResponse({"error": "Detector not found"}, status=404)

    if not detector.active:
        return JsonResponse({"error": "Detector is not active"}, status=400)

    try:
        # Queue detector execution
        task = run_detector.delay(detector_id)

        return JsonResponse(
            {
                "success": True,
                "message": f"Detector '{detector.name}' execution queued",
                "task_id": task.id,
                "detector": {
                    "id": detector.id,
                    "name": detector.name,
                },
            }
        )
    except Exception as e:
        return JsonResponse({"error": f"Failed to queue detector: {str(e)}"}, status=500)


class SystemStatsAPIView(View):
    """API endpoint for system statistics and health metrics."""

    def get(self, request):
        """Return comprehensive system statistics."""
        now = timezone.now()
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)

        # Detector statistics
        detector_stats = {
            "total": Detector.objects.count(),
            "active": Detector.objects.filter(active=True).count(),
            "recent_runs": Detector.objects.filter(last_run__gte=now - timedelta(hours=24)).count(),
            "scheduled": Detector.objects.exclude(schedule__isnull=True).count(),
        }

        # Detection statistics
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_start = today_start + timedelta(days=1)

        detection_stats = {
            "total": Detection.objects.count(),
            "pending": Detection.objects.filter(status="pending").count(),
            "processed_today": Detection.objects.filter(status="processed", processed_at__gte=today_start, processed_at__lt=tomorrow_start).count(),
            "dismissed_today": Detection.objects.filter(status="dismissed", processed_at__gte=today_start, processed_at__lt=tomorrow_start).count(),
            "high_confidence": Detection.objects.filter(confidence_score__gte=0.8).count(),
            "recent_24h": Detection.objects.filter(detection_timestamp__gte=now - timedelta(hours=24)).count(),
            "recent_7d": Detection.objects.filter(detection_timestamp__gte=week_ago).count(),
            "recent_30d": Detection.objects.filter(detection_timestamp__gte=month_ago).count(),
        }

        # Detection trends
        daily_detections = (
            Detection.objects.filter(detection_timestamp__gte=week_ago).extra(select={"day": "date(detection_timestamp)"}).values("day").annotate(count=Count("id")).order_by("day")
        )

        # Status breakdown
        status_breakdown = Detection.objects.values("status").annotate(count=Count("id"))

        # Template statistics
        template_stats = {
            "total": AlertTemplate.objects.count(),
            "active": AlertTemplate.objects.filter(active=True).count(),
            "shock_types_covered": AlertTemplate.objects.values("shock_type").distinct().count(),
        }

        return JsonResponse(
            {
                "timestamp": now.isoformat(),
                "detector_stats": detector_stats,
                "detection_stats": detection_stats,
                "template_stats": template_stats,
                "trends": {
                    "daily_detections": list(daily_detections),
                    "status_breakdown": list(status_breakdown),
                },
                "system_health": {
                    "detectors_with_recent_activity": Detector.objects.filter(last_run__gte=now - timedelta(hours=48)).count(),
                    "pending_detections_rate": (detection_stats["pending"] / max(detection_stats["total"], 1)) * 100,
                    "high_confidence_rate": (detection_stats["high_confidence"] / max(detection_stats["total"], 1)) * 100,
                },
            }
        )


@csrf_exempt
@require_http_methods(["POST"])
def detection_action_api(request, detection_id):
    """API endpoint for taking actions on detections."""
    try:
        detection = Detection.objects.get(id=detection_id)
    except Detection.DoesNotExist:
        return JsonResponse({"error": "Detection not found"}, status=404)

    action = request.POST.get("action")
    if not action:
        return JsonResponse({"error": "Action parameter required"}, status=400)

    try:
        if action == "process":
            if detection.status != "pending":
                return JsonResponse({"error": "Detection is not pending"}, status=400)
            detection.status = "processed"
            detection.save()
            message = "Detection processed successfully"

        elif action == "dismiss":
            if detection.status != "pending":
                return JsonResponse({"error": "Detection is not pending"}, status=400)
            detection.status = "dismissed"
            detection.save()
            message = "Detection dismissed successfully"

        elif action == "mark_duplicate":
            original_id = request.POST.get("original_id")
            if not original_id:
                return JsonResponse({"error": "Original detection ID required for duplicates"}, status=400)

            try:
                Detection.objects.get(id=original_id)  # Just verify it exists
                detection.status = "dismissed"
                detection.detection_data = detection.detection_data or {}
                detection.detection_data["duplicate_of"] = original_id
                detection.save()
                message = f"Detection marked as duplicate of #{original_id}"
            except Detection.DoesNotExist:
                return JsonResponse({"error": "Original detection not found"}, status=400)

        else:
            return JsonResponse({"error": "Invalid action"}, status=400)

        return JsonResponse(
            {
                "success": True,
                "message": message,
                "detection": {
                    "id": detection.id,
                    "status": detection.status,
                    "updated_at": timezone.now().isoformat(),
                },
            }
        )

    except Exception as e:
        return JsonResponse({"error": f"Action failed: {str(e)}"}, status=500)
