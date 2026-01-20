"""Views for alert framework detector management."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import DetailView, ListView

from alert_framework.forms import DetectorConfigurationHelpMixin, DetectorEditForm
from alert_framework.models import (
    AlertTemplate,
    Detection,
    Detector,
)
from alert_framework.tasks import run_detector


class DetectorListView(ListView):
    """List all detectors with filtering and search."""

    model = Detector
    template_name = "alert_framework/detector_list.html"
    context_object_name = "detectors"
    paginate_by = 20

    def get_queryset(self):
        """Filter detectors based on search and status."""
        queryset = Detector.objects.select_related("schedule").annotate(
            total_detections=Count("detections"),
            pending_detections=Count("detections", filter=Q(detections__status="pending")),
        )

        # Search functionality
        search = self.request.GET.get("search")
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(description__icontains=search) | Q(class_name__icontains=search))

        # Filter by status
        status = self.request.GET.get("status")
        if status == "active":
            queryset = queryset.filter(active=True)
        elif status == "inactive":
            queryset = queryset.filter(active=False)

        return queryset.order_by("-last_run", "name")

    def get_context_data(self, **kwargs):
        """Add additional context for the template."""
        context = super().get_context_data(**kwargs)
        context["search"] = self.request.GET.get("search", "")
        context["status_filter"] = self.request.GET.get("status", "")

        # Summary statistics
        context["stats"] = {
            "total_detectors": Detector.objects.count(),
            "active_detectors": Detector.objects.filter(active=True).count(),
            "pending_detections": Detection.objects.filter(status="pending").count(),
            "recent_runs": Detector.objects.filter(last_run__gte=timezone.now() - timezone.timedelta(days=1)).count(),
        }

        return context


class DetectorDetailView(DetailView):
    """Detailed view of a specific detector."""

    model = Detector
    template_name = "alert_framework/detector_detail.html"
    context_object_name = "detector"

    def get_context_data(self, **kwargs):
        """Add detection history and performance metrics."""
        context = super().get_context_data(**kwargs)
        detector = self.object

        # Recent detections
        context["recent_detections"] = (
            detector.detections.select_related("shock_type", "duplicate_of__detector").prefetch_related("locations__admin_level").order_by("-created_at")[:10]
        )

        # Detection statistics
        detections = detector.detections.all()
        context["detection_stats"] = {
            "total": detections.count(),
            "pending": detections.filter(status="pending").count(),
            "processed": detections.filter(status="processed").count(),
            "dismissed": detections.filter(status="dismissed").count(),
            "duplicates": detections.filter(duplicate_of__isnull=False).count(),
        }

        # Performance metrics
        if detector.run_count > 0:
            context["performance"] = {
                "avg_detections_per_run": detector.detection_count / detector.run_count,
                "success_rate": detector.success_rate,  # From model property
                "last_run": detector.last_run,  # Pass datetime object directly for timesince filter
            }

        return context


@method_decorator(login_required, name="dispatch")
class DetectorRunView(View):
    """Manually trigger detector execution."""

    def post(self, request, pk):
        """Start detector execution as background task."""
        detector = get_object_or_404(Detector, pk=pk)

        if not detector.active:
            messages.error(request, f"Cannot run inactive detector: {detector.name}")
            return redirect("alert_framework:detector_detail", pk=pk)

        try:
            # Start detector execution as Celery task
            task_result = run_detector.delay(detector.id)

            messages.success(request, f'Detector "{detector.name}" execution started. Task ID: {task_result.id}')

        except Exception as e:
            messages.error(request, f"Failed to start detector execution: {str(e)}")

        return redirect("alert_framework:detector_detail", pk=pk)


@method_decorator(login_required, name="dispatch")
class DetectorEditView(View):
    """Edit detector configuration."""

    def get(self, request, pk):
        """Display detector edit form."""
        detector = get_object_or_404(Detector, pk=pk)
        form = DetectorEditForm(instance=detector)

        # Get configuration help for this detector type
        detector_class_name = detector.class_name.split(".")[-1] if detector.class_name else "Unknown"
        config_help = DetectorConfigurationHelpMixin.get_config_help(detector_class_name)

        context = {
            "detector": detector,
            "form": form,
            "config_help": config_help,
            "detector_class_name": detector_class_name,
        }

        return render(request, "alert_framework/detector_edit.html", context)

    def post(self, request, pk):
        """Process detector edit form submission."""
        detector = get_object_or_404(Detector, pk=pk)
        form = DetectorEditForm(request.POST, instance=detector)

        if form.is_valid():
            try:
                form.save()
                messages.success(request, f'Detector "{detector.name}" updated successfully.')
                return redirect("alert_framework:detector_detail", pk=pk)
            except Exception as e:
                messages.error(request, f"Error saving detector: {str(e)}")
        else:
            messages.error(request, "Please correct the errors below.")

        # Get configuration help for this detector type
        detector_class_name = detector.class_name.split(".")[-1] if detector.class_name else "Unknown"
        config_help = DetectorConfigurationHelpMixin.get_config_help(detector_class_name)

        context = {
            "detector": detector,
            "form": form,
            "config_help": config_help,
            "detector_class_name": detector_class_name,
        }

        return render(request, "alert_framework/detector_edit.html", context)


class DetectionListView(ListView):
    """List detections with filtering and search."""

    model = Detection
    template_name = "alert_framework/detection_list.html"
    context_object_name = "detections"
    paginate_by = 50

    def get_queryset(self):
        """Filter detections based on parameters."""
        queryset = (
            Detection.objects.select_related(
                "detector",
                "shock_type",
                "duplicate_of__detector",
            )
            .prefetch_related(
                "locations__admin_level",
                "duplicates__detector",
            )
            .order_by("-created_at")
        )

        # Filter by detector
        detector_id = self.request.GET.get("detector")
        if detector_id:
            queryset = queryset.filter(detector_id=detector_id)

        # Filter by status
        status = self.request.GET.get("status")
        if status:
            queryset = queryset.filter(status=status)

        # Filter by shock type
        shock_type = self.request.GET.get("shock_type")
        if shock_type:
            queryset = queryset.filter(shock_type_id=shock_type)

        # Exclude/include duplicates
        show_duplicates = self.request.GET.get("show_duplicates")
        if not show_duplicates:
            queryset = queryset.filter(duplicate_of__isnull=True)

        return queryset

    def get_context_data(self, **kwargs):
        """Add filter context and statistics."""
        context = super().get_context_data(**kwargs)

        # Filter options
        context["detectors"] = Detector.objects.filter(active=True).order_by("name")
        context["shock_types"] = Detection.objects.values_list("shock_type__id", "shock_type__name").distinct().order_by("shock_type__name")

        # Current filters
        context["filters"] = {
            "detector": self.request.GET.get("detector", ""),
            "status": self.request.GET.get("status", ""),
            "shock_type": self.request.GET.get("shock_type", ""),
            "show_duplicates": self.request.GET.get("show_duplicates", False),
        }

        # Statistics
        context["stats"] = {
            "total_detections": Detection.objects.count(),
            "pending": Detection.objects.filter(status="pending").count(),
            "processed": Detection.objects.filter(status="processed").count(),
            "dismissed": Detection.objects.filter(status="dismissed").count(),
            "recent_24h": Detection.objects.filter(created_at__gte=timezone.now() - timezone.timedelta(days=1)).count(),
        }

        return context


class DetectionDetailView(DetailView):
    """Detailed view of a specific detection."""

    model = Detection
    template_name = "alert_framework/detection_detail.html"
    context_object_name = "detection"

    def get_context_data(self, **kwargs):
        """Add related detections and processing history."""
        context = super().get_context_data(**kwargs)
        detection = self.object

        # Related detections (duplicates or original)
        if detection.duplicate_of:
            # This is a duplicate, show the original and other duplicates
            context["original_detection"] = detection.duplicate_of
            context["related_detections"] = Detection.objects.filter(duplicate_of=detection.duplicate_of).exclude(id=detection.id).order_by("created_at")
        else:
            # This might be the original, show its duplicates
            context["duplicates"] = detection.duplicates.order_by("created_at")

        # Processing information
        context["processing_info"] = {
            "duration": detection.processing_duration,
            "is_duplicate": detection.is_duplicate,
        }

        # Add source data point for embedding in template
        context["data_point"] = detection.source_data_point

        return context


@login_required
def detection_action_view(request, pk):
    """Handle detection actions (process, dismiss, mark duplicate)."""
    if request.method != "POST":
        return JsonResponse({"error": "POST method required"}, status=405)

    detection = get_object_or_404(Detection, pk=pk)
    action = request.POST.get("action")

    try:
        if action == "process":
            # Mark as processed (placeholder - would generate actual alert)
            detection.mark_processed()
            message = f"Detection {detection.id} marked as processed"

        elif action == "dismiss":
            detection.mark_dismissed()
            message = f"Detection {detection.id} dismissed"

        elif action == "mark_duplicate":
            original_id = request.POST.get("original_id")
            if not original_id:
                return JsonResponse({"error": "Original detection ID required"}, status=400)

            original = get_object_or_404(Detection, pk=original_id)
            detection.mark_duplicate(original)
            message = f"Detection {detection.id} marked as duplicate of {original.id}"

        else:
            return JsonResponse({"error": "Invalid action"}, status=400)

        # For AJAX requests, return JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({"success": True, "message": message, "new_status": detection.status})

        # For form submissions, redirect back to detection detail
        messages.success(request, message)
        return redirect('alert_framework:detection_detail', pk=detection.pk)

    except Exception as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({"error": str(e)}, status=500)

        messages.error(request, f"Error processing action: {str(e)}")
        return redirect('alert_framework:detection_detail', pk=detection.pk)


class AlertTemplateListView(ListView):
    """List alert templates."""

    model = AlertTemplate
    template_name = "alert_framework/template_list.html"
    context_object_name = "templates"

    def get_queryset(self):
        """Get templates with related shock types."""
        return AlertTemplate.objects.select_related("shock_type").order_by("shock_type__name", "name")

    def get_context_data(self, **kwargs):
        """Add template statistics."""
        context = super().get_context_data(**kwargs)
        context["stats"] = {
            "total_templates": AlertTemplate.objects.count(),
            "active_templates": AlertTemplate.objects.filter(active=True).count(),
            "shock_types_covered": AlertTemplate.objects.values("shock_type").distinct().count(),
        }
        return context


class AlertTemplateDetailView(DetailView):
    """Detailed view of alert template."""

    model = AlertTemplate
    template_name = "alert_framework/template_detail.html"
    context_object_name = "alert_template"

    def get_context_data(self, **kwargs):
        """Add usage statistics and preview."""
        context = super().get_context_data(**kwargs)
        alert_template = self.object

        # Usage statistics
        context["usage_stats"] = {
            "detections_with_shock_type": Detection.objects.filter(
                shock_type=alert_template.shock_type
            ).count(),
            "recent_usage": Detection.objects.filter(
                shock_type=alert_template.shock_type,
                created_at__gte=timezone.now() - timezone.timedelta(days=30)
            ).count(),
        }

        # Template preview with sample data
        sample_context = {
            "detector_name": "Sample Detector",
            "detection_timestamp": timezone.now(),
            "confidence_score": 0.85,
            "location_names": ["Khartoum", "Omdurman"],
            "primary_location": {"name": "Khartoum"},
            "shock_type": alert_template.shock_type.name if alert_template.shock_type else "Unknown",
        }

        # Temporarily disable template preview to avoid template syntax issues
        context["preview"] = None
        context["preview_error"] = "Preview temporarily disabled"

        return context


def dashboard_view(request):
    """Main dashboard showing system overview."""
    context = {
        "detector_stats": {
            "total": Detector.objects.count(),
            "active": Detector.objects.filter(active=True).count(),
            "recent_runs": Detector.objects.filter(last_run__gte=timezone.now() - timezone.timedelta(hours=24)).count(),
        },
        "detection_stats": {
            "total": Detection.objects.count(),
            "pending": Detection.objects.filter(status="pending").count(),
            "processed_today": Detection.objects.filter(processed_at__gte=timezone.now().replace(hour=0, minute=0, second=0)).count(),
            "recent": Detection.objects.filter(created_at__gte=timezone.now() - timezone.timedelta(hours=24)).count(),
        },
        "recent_detections": Detection.objects.select_related("detector", "shock_type").prefetch_related("locations__admin_level").order_by("-created_at")[:10],
        "active_detectors": Detector.objects.filter(active=True).order_by("name"),
    }

    return render(request, "alert_framework/dashboard.html", context)
