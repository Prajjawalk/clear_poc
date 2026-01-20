"""Views for alerts app."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Prefetch, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView

from .forms import AlertFeedbackForm, AlertForm, SubscriptionForm
from .models import Alert, ShockType, Subscription, UserAlert
from .utils import UserAlertManager, AlertQueryBuilder, ResponseHelper
from .exceptions import APIErrorHandler, api_error_handler, ValidationError


class AlertListView(LoginRequiredMixin, ListView):
    """List view for alerts with filtering and user interactions."""

    model = Alert
    template_name = "alerts/alert_list.html"
    context_object_name = "alerts"
    paginate_by = 20

    def get_queryset(self):
        """Get filtered alerts with user interaction data."""
        queryset = Alert.objects.filter(go_no_go=True).select_related("shock_type", "data_source").prefetch_related("locations")

        # Filter by shock type
        shock_type = self.request.GET.get("shock_type")
        if shock_type:
            queryset = queryset.filter(shock_type_id=shock_type)

        # Filter by severity
        severity = self.request.GET.get("severity")
        if severity:
            queryset = queryset.filter(severity=severity)

        # Filter by data source
        source = self.request.GET.get("source")
        if source:
            queryset = queryset.filter(data_source_id=source)

        # Filter by admin1 location
        admin1 = self.request.GET.get("admin1")
        if admin1:
            queryset = queryset.filter(locations__id=admin1).distinct()

        # Filter by detector
        detector = self.request.GET.get("detector")
        if detector:
            from alert_framework.models import Detection
            # Get alerts that have detections from the specified detector
            alert_ids = Detection.objects.filter(detector_id=detector).values_list('alert_id', flat=True)
            queryset = queryset.filter(id__in=alert_ids)

        # Filter by date range
        date_from = self.request.GET.get("date_from")
        date_to = self.request.GET.get("date_to")
        if date_from:
            queryset = queryset.filter(shock_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(shock_date__lte=date_to)

        # Filter by active today (default: checked unless explicitly unchecked)
        active_today = self.request.GET.get("active_today")
        if active_today != "0":  # Default to active, unless explicitly set to "0"
            from django.utils import timezone
            today = timezone.now()
            queryset = queryset.filter(valid_from__lte=today, valid_until__gte=today)

        # Filter by bookmarked (if requested)
        if self.request.GET.get("bookmarked"):
            queryset = queryset.filter(useralert__user=self.request.user, useralert__bookmarked=True)

        # Search in title and text
        search = self.request.GET.get("search")
        if search:
            queryset = queryset.filter(Q(title__icontains=search) | Q(text__icontains=search))

        # Prefetch user interactions
        user_alerts = UserAlert.objects.filter(user=self.request.user)
        queryset = queryset.prefetch_related(Prefetch("useralert_set", queryset=user_alerts, to_attr="user_interactions"))

        return queryset.order_by("-shock_date", "-created_at")

    def get_context_data(self, **kwargs):
        """Add filter options to context."""
        from data_pipeline.models import Source
        from location.models import Location
        from alert_framework.models import Detector

        context = super().get_context_data(**kwargs)
        context["shock_types"] = ShockType.objects.all()
        context["severity_choices"] = Alert.SEVERITY_CHOICES

        # Get sources that have alerts
        context["sources"] = Source.objects.filter(alert__isnull=False).distinct().order_by('name')

        # Get admin1 locations (locations with admin_level code '1')
        context["admin1_locations"] = Location.objects.filter(admin_level__code='1').order_by('name')

        # Get detectors that have generated alerts
        context["detectors"] = Detector.objects.filter(detections__alert__isnull=False).distinct().order_by('name')

        # Add current filter values
        context["current_filters"] = {
            "shock_type": self.request.GET.get("shock_type", ""),
            "severity": self.request.GET.get("severity", ""),
            "source": self.request.GET.get("source", ""),
            "admin1": self.request.GET.get("admin1", ""),
            "detector": self.request.GET.get("detector", ""),
            "date_from": self.request.GET.get("date_from", ""),
            "date_to": self.request.GET.get("date_to", ""),
            "active_today": self.request.GET.get("active_today", "1"),  # Default to "1" (checked)
            "bookmarked": self.request.GET.get("bookmarked", ""),
            "search": self.request.GET.get("search", ""),
        }

        return context


class AlertDetailView(LoginRequiredMixin, DetailView):
    """Detail view for individual alert with user interactions."""

    model = Alert
    template_name = "alerts/alert_detail.html"
    context_object_name = "alert"

    def get_object(self):
        """Get alert and mark as read for current user."""
        alert = get_object_or_404(
            Alert.objects.select_related("shock_type", "data_source").prefetch_related("locations"),
            pk=self.kwargs["pk"], go_no_go=True
        )

        # Mark as read using utility
        UserAlertManager.mark_as_read(self.request.user, alert)

        return alert

    def get_context_data(self, **kwargs):
        """Add user interaction data to context."""
        context = super().get_context_data(**kwargs)

        # Use utility to get user interaction
        context["user_alert"] = UserAlertManager.get_user_interaction(self.request.user, self.object)
        context["feedback_form"] = AlertFeedbackForm()

        # Add source data point for embedding in template
        context["data_point"] = self.object.source_data_point

        return context


class AlertCreateView(UserPassesTestMixin, CreateView):
    """Create view for alerts (staff only)."""

    model = Alert
    form_class = AlertForm
    template_name = "alerts/alert_form.html"
    success_url = reverse_lazy("alerts:alert_list")

    def test_func(self):
        """Only allow staff users to create alerts."""
        return self.request.user.is_staff

    def form_valid(self, form):
        """Set go_no_go to True by default and add success message."""
        form.instance.go_no_go = True
        messages.success(self.request, "Alert created successfully.")
        return super().form_valid(form)


class SubscriptionListView(LoginRequiredMixin, ListView):
    """List view for user subscriptions."""

    model = Subscription
    template_name = "alerts/subscription_list.html"
    context_object_name = "subscriptions"

    def get_queryset(self):
        """Get subscriptions for current user."""
        return Subscription.objects.filter(user=self.request.user).prefetch_related("locations", "shock_types")


class SubscriptionCreateView(LoginRequiredMixin, CreateView):
    """Create view for subscriptions."""

    model = Subscription
    form_class = SubscriptionForm
    template_name = "alerts/subscription_form.html"
    success_url = reverse_lazy("alerts:subscription_list")

    def form_valid(self, form):
        """Set user for the subscription."""
        form.instance.user = self.request.user
        messages.success(self.request, "Subscription created successfully.")
        return super().form_valid(form)


class SubscriptionUpdateView(LoginRequiredMixin, UpdateView):
    """Update view for subscriptions."""

    model = Subscription
    form_class = SubscriptionForm
    template_name = "alerts/subscription_form.html"
    success_url = reverse_lazy("alerts:subscription_list")

    def get_queryset(self):
        """Only allow users to edit their own subscriptions."""
        return Subscription.objects.filter(user=self.request.user)

    def form_valid(self, form):
        """Add success message on subscription update."""
        messages.success(self.request, "Subscription updated successfully.")
        return super().form_valid(form)


class SubscriptionDeleteView(LoginRequiredMixin, DeleteView):
    """Delete view for subscriptions."""

    model = Subscription
    template_name = "alerts/subscription_confirm_delete.html"
    success_url = reverse_lazy("alerts:subscription_list")

    def get_queryset(self):
        """Only allow users to delete their own subscriptions."""
        return Subscription.objects.filter(user=self.request.user)

    def delete(self, request, *args, **kwargs):
        """Add success message on subscription deletion."""
        messages.success(request, "Subscription deleted successfully.")
        return super().delete(request, *args, **kwargs)


class AlertMapView(LoginRequiredMixin, TemplateView):
    """Map view showing alerts geographically."""

    template_name = "alerts/alert_map.html"

    def get_context_data(self, **kwargs):
        """Add alerts with location data to context."""
        import json
        context = super().get_context_data(**kwargs)

        # Get alerts with location data
        alerts = Alert.objects.filter(go_no_go=True).select_related("shock_type", "data_source").prefetch_related("locations").order_by("-shock_date")[:100]

        # Serialize alerts data for JavaScript consumption
        alerts_data = []
        for alert in alerts:
            alert_data = {
                'id': alert.id,
                'title': alert.title,
                'text': alert.text,
                'shock_date': alert.shock_date.isoformat(),
                'severity': alert.severity,
                'severity_display': alert.severity_display,
                'valid_from': alert.valid_from.isoformat(),
                'valid_until': alert.valid_until.isoformat(),
                'is_active': alert.is_active,
                'shock_type': {
                    'id': alert.shock_type.id,
                    'name': alert.shock_type.name,
                    'icon': alert.shock_type.icon,
                    'color': alert.shock_type.color,
                    'css_class': alert.shock_type.css_class
                },
                'data_source': {
                    'id': alert.data_source.id,
                    'name': alert.data_source.name
                },
                'locations': [
                    {
                        'id': location.id,
                        'name': location.name,
                        'geo_id': location.geo_id,
                        'point': {
                            'coordinates': [location.point.x, location.point.y] if location.point else None
                        } if location.point else None,
                    }
                    for location in alert.locations.all()
                ]
            }
            alerts_data.append(alert_data)

        context["alerts"] = alerts
        context["alerts_json"] = json.dumps(alerts_data)
        context["shock_types"] = ShockType.objects.all()
        context["severity_choices"] = Alert.SEVERITY_CHOICES
        
        # Add shock types configuration for JavaScript
        shock_types_config = {}
        for shock_type in ShockType.objects.all():
            shock_types_config[shock_type.name] = {
                'icon': shock_type.icon,
                'color': shock_type.color,
                'css_class': shock_type.css_class
            }
        context["shock_types_config_json"] = json.dumps(shock_types_config)

        return context


@login_required
@require_POST
@api_error_handler
def rate_alert(request, alert_id):
    """AJAX endpoint to rate an alert."""
    alert = get_object_or_404(Alert, pk=alert_id, go_no_go=True)
    rating_value = request.POST.get("rating")

    rating = ResponseHelper.validate_rating(rating_value)
    UserAlertManager.set_rating(request.user, alert, rating)

    return APIErrorHandler.success_response({"rating": rating}, "Rating saved successfully")


@login_required
@require_POST
@api_error_handler
def toggle_bookmark(request, alert_id):
    """AJAX endpoint to toggle alert bookmark."""
    alert = get_object_or_404(Alert, pk=alert_id, go_no_go=True)

    user_alert, is_bookmarked = UserAlertManager.toggle_bookmark(request.user, alert)

    return APIErrorHandler.success_response({"bookmarked": is_bookmarked}, "Bookmark status updated")


@login_required
@require_POST
@api_error_handler
def flag_alert(request, alert_id):
    """AJAX endpoint to flag an alert as false/incomplete."""
    alert = get_object_or_404(Alert, pk=alert_id, go_no_go=True)
    flag_type = request.POST.get("flag_type")

    validated_flag_type = ResponseHelper.validate_flag_type(flag_type)
    user_alert, is_flagged = UserAlertManager.toggle_flag(request.user, alert, validated_flag_type)

    return APIErrorHandler.success_response({"flagged": is_flagged}, f"Alert {flag_type} flag updated")


@login_required
@require_POST
@api_error_handler
def add_feedback(request, alert_id):
    """AJAX endpoint to add feedback comment to an alert."""
    alert = get_object_or_404(Alert, pk=alert_id, go_no_go=True)
    form = AlertFeedbackForm(request.POST)

    if form.is_valid():
        comment = form.cleaned_data["comment"]
        user_alert = UserAlertManager.add_comment(request.user, alert, comment)

        return APIErrorHandler.success_response({"comment": user_alert.comment}, "Feedback added successfully")

    # Handle form validation errors
    return APIErrorHandler.handle_error(ValidationError(form.errors), request)
