"""Views for the django tests project."""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import connection
from django.http import HttpResponse
from django.shortcuts import render
from django.views import View

from translation.utils import translate


class HealthcheckView(View):
    """Handle health check requests."""

    def get(self, request):
        """
        Return health check status.

        Provides an unauthenticated health check page, returning 'ok' if Django is up and running
        and can access the backend database, 'nok' otherwise.
        """
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            one = cursor.fetchone()[0]
            if one == 1:
                return HttpResponse("ok")
        return HttpResponse("nok")


class HomeView(LoginRequiredMixin, View):
    """Main homepage with links to all applications."""

    def get(self, request):
        """Render homepage with application links."""
        applications = [
            {
                "name": translate("Data Pipeline"),
                "description": translate("Manage data sources, variables, and processing workflows"),
                "url": "/pipeline/",
                "icon": "bi-diagram-3",
                "color": "primary",
                "features": [translate("Source Management"), translate("Variable Configuration"), translate("Data Processing"), translate("API Access")],
            },
            {
                "name": translate("Location Management"),
                "description": translate("Geographic location and gazetteer management system"),
                "url": "/location/",
                "icon": "bi-geo-alt",
                "color": "success",
                "features": [translate("Location Hierarchy"), translate("Gazetteer Entries"), translate("Location Matching"), translate("GIS Integration")],
            },
            {
                "name": translate("Task Monitoring"),
                "description": translate("Background task execution monitoring and statistics"),
                "url": "/tasks/",
                "icon": "bi-activity",
                "color": "warning",
                "features": [translate("Task Execution"), translate("Performance Stats"), translate("Error Tracking"), translate("Real-time Updates")],
            },
            {
                "name": translate("Alert System"),
                "description": translate("Public alert interface with map visualization and subscriptions"),
                "url": "/alerts/",
                "icon": "bi-bell",
                "color": "danger",
                "features": [translate("Alert Management"), translate("Map Visualization"), translate("User Subscriptions"), translate("Interactive Feedback")],
            },
            {
                "name": translate("Alert Framework"),
                "description": translate("Internal alert detection and management system"),
                "url": "/alert_framework/",
                "icon": "bi-shield-exclamation",
                "color": "warning",
                "features": [translate("Detection Management"), translate("Alert Configuration"), translate("System Monitoring"), translate("Framework Administration")],
            },
            {
                "name": translate("LLM Service"),
                "description": translate("Large Language Model query interface and testing platform"),
                "url": "/llm/",
                "icon": "bi-cpu",
                "color": "dark",
                "features": [translate("Query Interface"), translate("Provider Status"), translate("Usage Statistics"), translate("Performance Monitoring")],
            },
            {
                "name": translate("API Documentation"),
                "description": translate("Comprehensive API reference and endpoint documentation"),
                "url": "/api/",
                "icon": "bi-code-slash",
                "color": "info",
                "features": [translate("REST Endpoints"), translate("Parameter Reference"), translate("Response Examples"), translate("Interactive Testing")],
            },
            {
                "name": translate("User Management"),
                "description": translate("User profile management, notification preferences, and admin tools"),
                "url": "/users/",
                "icon": "bi-people",
                "color": "success",
                "features": [translate("Profile Management"), translate("Email Notifications"), translate("User Administration"), translate("Notification Settings")],
            },
        ]

        context = {"applications": applications, "title": translate("NRC EWAS - Early Warning and Alert System")}

        return render(request, "home.html", context)


class APIDocumentationView(LoginRequiredMixin, View):
    """Comprehensive API documentation."""

    def get(self, request):
        """Render API documentation page."""
        api_endpoints = {
            "Data Pipeline": {
                "base_url": "/pipeline/api/",
                "endpoints": [
                    {
                        "method": "GET",
                        "path": "/pipeline/api/sources/",
                        "description": "List all data sources with optional filtering",
                        "parameters": [
                            {"name": "name", "type": "string", "description": "Filter by source name"},
                            {"name": "type", "type": "string", "description": "Filter by source type"},
                            {"name": "status", "type": "string", "description": "Filter by status (active, inactive)"},
                        ],
                        "response": "Array of source objects with metadata",
                    },
                    {
                        "method": "GET",
                        "path": "/pipeline/api/variables/",
                        "description": "List all variables with optional source filtering",
                        "parameters": [
                            {"name": "source", "type": "integer", "description": "Filter by source ID"},
                            {"name": "name", "type": "string", "description": "Filter by variable name"},
                            {"name": "type", "type": "string", "description": "Filter by data type"},
                        ],
                        "response": "Array of variable objects with source relationships",
                    },
                    {
                        "method": "GET",
                        "path": "/pipeline/api/data/",
                        "description": "Query data records (coming soon)",
                        "parameters": [],
                        "response": "Coming soon",
                        "status": "planned",
                    },
                    {
                        "method": "GET",
                        "path": "/pipeline/api/statistics/",
                        "description": "Get pipeline statistics (coming soon)",
                        "parameters": [],
                        "response": "Coming soon",
                        "status": "planned",
                    },
                ],
            },
            "Location Management": {
                "base_url": "/location/api/",
                "endpoints": [
                    {
                        "method": "GET",
                        "path": "/location/api/locations/",
                        "description": "List locations with filtering and pagination",
                        "parameters": [
                            {"name": "name", "type": "string", "description": "Filter by location name"},
                            {"name": "admin_level", "type": "integer", "description": "Filter by admin level ID"},
                            {"name": "parent", "type": "integer", "description": "Filter by parent location ID"},
                            {"name": "page", "type": "integer", "description": "Page number for pagination"},
                            {"name": "page_size", "type": "integer", "description": "Number of results per page"},
                        ],
                        "response": "Paginated array of location objects with hierarchy info",
                    },
                    {
                        "method": "GET",
                        "path": "/location/api/admin-levels/",
                        "description": "List administrative level definitions",
                        "parameters": [],
                        "response": "Array of admin level objects (country, state, district, etc.)",
                    },
                    {
                        "method": "POST",
                        "path": "/location/api/match/",
                        "description": "Match location names to database entries",
                        "parameters": [
                            {"name": "name", "type": "string", "description": "Location name to match"},
                            {"name": "admin_level", "type": "integer", "description": "Expected admin level (optional)"},
                            {"name": "parent", "type": "integer", "description": "Parent location for context (optional)"},
                        ],
                        "response": "Best matching location with confidence score",
                    },
                    {
                        "method": "POST",
                        "path": "/location/api/bulk-match/",
                        "description": "Bulk match multiple location names",
                        "parameters": [
                            {"name": "locations", "type": "array", "description": "Array of location names to match"},
                        ],
                        "response": "Array of matched locations with confidence scores",
                    },
                    {
                        "method": "GET",
                        "path": "/location/api/locations/{id}/hierarchy/",
                        "description": "Get location hierarchy and children",
                        "parameters": [
                            {"name": "id", "type": "integer", "description": "Location ID"},
                        ],
                        "response": "Location object with parent hierarchy and children",
                    },
                ],
            },
            "Task Monitoring": {
                "base_url": "/tasks/api/",
                "endpoints": [
                    {
                        "method": "GET",
                        "path": "/tasks/api/executions/",
                        "description": "List task executions with filtering",
                        "parameters": [
                            {"name": "task_type", "type": "integer", "description": "Filter by task type ID"},
                            {"name": "status", "type": "string", "description": "Filter by execution status"},
                            {"name": "start_date", "type": "datetime", "description": "Filter executions after date"},
                            {"name": "end_date", "type": "datetime", "description": "Filter executions before date"},
                        ],
                        "response": "Array of task execution objects with timing and status",
                    },
                    {
                        "method": "GET",
                        "path": "/tasks/api/types/",
                        "description": "List task types with statistics",
                        "parameters": [],
                        "response": "Array of task type objects with execution statistics",
                    },
                    {
                        "method": "GET",
                        "path": "/tasks/api/statistics/",
                        "description": "Get task execution statistics",
                        "parameters": [
                            {"name": "period", "type": "string", "description": "Time period (day, week, month)"},
                        ],
                        "response": "Aggregated statistics for task executions",
                    },
                ],
            },
            "Alert System": {
                "base_url": "/alerts/api/",
                "endpoints": [
                    {
                        "method": "GET",
                        "path": "/alerts/api/alerts/",
                        "description": "List alerts with user interactions (authenticated)",
                        "parameters": [
                            {"name": "shock_type", "type": "integer", "description": "Filter by shock type ID"},
                            {"name": "severity", "type": "integer", "description": "Filter by severity level (1-5)"},
                            {"name": "date_from", "type": "date", "description": "Filter alerts from date"},
                            {"name": "date_to", "type": "date", "description": "Filter alerts until date"},
                            {"name": "search", "type": "string", "description": "Search in title and content"},
                            {"name": "limit", "type": "integer", "description": "Maximum results (max 1000)"},
                        ],
                        "response": "Array of alert objects with user interactions",
                    },
                    {
                        "method": "GET",
                        "path": "/alerts/api/alert/{id}/",
                        "description": "Get detailed alert information (authenticated)",
                        "parameters": [
                            {"name": "id", "type": "integer", "description": "Alert ID"},
                        ],
                        "response": "Detailed alert object with full user interaction data",
                    },
                    {
                        "method": "GET",
                        "path": "/alerts/api/public/alerts/",
                        "description": "Public alerts API for external integrations",
                        "parameters": [
                            {"name": "shock_type", "type": "integer", "description": "Filter by shock type ID"},
                            {"name": "severity", "type": "integer", "description": "Filter by severity level (1-5)"},
                            {"name": "active_only", "type": "boolean", "description": "Show only currently active alerts (default: true)"},
                            {"name": "date_from", "type": "date", "description": "Filter alerts from date (ISO format)"},
                            {"name": "date_to", "type": "date", "description": "Filter alerts until date (ISO format)"},
                            {"name": "location_ids", "type": "string", "description": "Comma-separated location IDs"},
                            {"name": "search", "type": "string", "description": "Search in title and content"},
                            {"name": "page", "type": "integer", "description": "Page number for pagination"},
                            {"name": "page_size", "type": "integer", "description": "Results per page (max 100)"},
                        ],
                        "response": "Paginated array of public alert objects with community stats",
                    },
                    {
                        "method": "GET",
                        "path": "/alerts/api/public/shock-types/",
                        "description": "List shock types with alert counts (public)",
                        "parameters": [],
                        "response": "Array of shock type objects with alert counts and styling info",
                    },
                    {
                        "method": "GET",
                        "path": "/alerts/api/public/stats/",
                        "description": "Comprehensive alert statistics (public)",
                        "parameters": [],
                        "response": "Alert statistics including overview, breakdowns, and community engagement",
                    },
                    {
                        "method": "POST",
                        "path": "/alerts/webhook/alert/create/",
                        "description": "Webhook for external systems to create alerts",
                        "parameters": [
                            {"name": "title", "type": "string", "description": "Alert title (required)"},
                            {"name": "text", "type": "string", "description": "Alert content (required)"},
                            {"name": "shock_type_id", "type": "integer", "description": "Shock type ID (required)"},
                            {"name": "data_source_id", "type": "integer", "description": "Data source ID (required)"},
                            {"name": "shock_date", "type": "date", "description": "Event date in ISO format (required)"},
                            {"name": "severity", "type": "integer", "description": "Severity level 1-5 (required)"},
                            {"name": "valid_from", "type": "datetime", "description": "Alert validity start (optional)"},
                            {"name": "valid_until", "type": "datetime", "description": "Alert validity end (optional)"},
                            {"name": "location_ids", "type": "array", "description": "Array of location IDs (optional)"},
                            {"name": "go_no_go", "type": "boolean", "description": "Approval status (optional, default: false)"},
                        ],
                        "response": "Created alert object with ID and metadata",
                    },
                    {
                        "method": "GET",
                        "path": "/alerts/api/shock-types/",
                        "description": "List shock types with basic info (authenticated)",
                        "parameters": [],
                        "response": "Array of shock type objects with alert counts",
                    },
                    {
                        "method": "GET",
                        "path": "/alerts/api/subscriptions/",
                        "description": "List user subscriptions (authenticated)",
                        "parameters": [],
                        "response": "Array of user subscription objects with locations and shock types",
                    },
                    {
                        "method": "GET",
                        "path": "/alerts/api/stats/",
                        "description": "Alert statistics with user-specific data (authenticated)",
                        "parameters": [],
                        "response": "Alert statistics including user bookmarks, ratings, and subscriptions",
                    },
                ],
            },
            "Alert Framework": {
                "base_url": "/alert_framework/api/",
                "endpoints": [
                    {
                        "method": "GET",
                        "path": "/alert_framework/api/detectors/",
                        "description": "List alert detectors with filtering and pagination",
                        "parameters": [
                            {"name": "active", "type": "boolean", "description": "Filter by active status"},
                            {"name": "search", "type": "string", "description": "Search in detector name or description"},
                            {"name": "page", "type": "integer", "description": "Page number for pagination"},
                        ],
                        "response": "Paginated array of detector objects with statistics",
                    },
                    {
                        "method": "GET",
                        "path": "/alert_framework/api/detectors/{id}/",
                        "description": "Get detailed detector information and configuration",
                        "parameters": [
                            {"name": "id", "type": "integer", "description": "Detector ID"},
                        ],
                        "response": "Detector object with statistics and recent detections",
                    },
                    {
                        "method": "POST",
                        "path": "/alert_framework/api/detectors/{id}/run/",
                        "description": "Manually trigger detector execution",
                        "parameters": [
                            {"name": "id", "type": "integer", "description": "Detector ID"},
                        ],
                        "response": "Task execution confirmation with task ID",
                    },
                    {
                        "method": "GET",
                        "path": "/alert_framework/api/detections/",
                        "description": "List detections with advanced filtering",
                        "parameters": [
                            {"name": "detector", "type": "integer", "description": "Filter by detector ID"},
                            {"name": "status", "type": "string", "description": "Filter by status (pending, processed, dismissed)"},
                            {"name": "start_date", "type": "datetime", "description": "Filter detections from date (ISO format)"},
                            {"name": "end_date", "type": "datetime", "description": "Filter detections until date (ISO format)"},
                            {"name": "min_confidence", "type": "float", "description": "Minimum confidence threshold (0.0-1.0)"},
                            {"name": "page", "type": "integer", "description": "Page number for pagination"},
                        ],
                        "response": "Paginated array of detection objects with locations",
                    },
                    {
                        "method": "GET",
                        "path": "/alert_framework/api/detections/{id}/",
                        "description": "Get detailed detection information",
                        "parameters": [
                            {"name": "id", "type": "integer", "description": "Detection ID"},
                        ],
                        "response": "Detection object with full metadata and location details",
                    },
                    {
                        "method": "POST",
                        "path": "/alert_framework/api/detections/{id}/action/",
                        "description": "Take actions on detections (process, dismiss, mark duplicate)",
                        "parameters": [
                            {"name": "id", "type": "integer", "description": "Detection ID"},
                            {"name": "action", "type": "string", "description": "Action to take (process, dismiss, mark_duplicate)"},
                            {"name": "original_id", "type": "integer", "description": "Original detection ID (required for mark_duplicate)"},
                        ],
                        "response": "Action confirmation with updated detection status",
                    },
                    {
                        "method": "GET",
                        "path": "/alert_framework/api/stats/",
                        "description": "Comprehensive alert framework statistics and health metrics",
                        "parameters": [],
                        "response": "System statistics including detector performance, detection trends, and health metrics",
                    },
                ],
            },
            "LLM Service": {
                "base_url": "/llm/api/",
                "endpoints": [
                    {
                        "method": "POST",
                        "path": "/llm/api/query/",
                        "description": "Send queries to Large Language Models with support for streaming responses",
                        "parameters": [
                            {"name": "prompt", "type": "string", "description": "The input prompt for the LLM (required)"},
                            {"name": "provider", "type": "string", "description": "LLM provider name (optional, uses default if not specified)"},
                            {"name": "model", "type": "string", "description": "Model name (optional, uses provider default)"},
                            {"name": "temperature", "type": "float", "description": "Sampling temperature between 0.0 and 1.0 (optional)"},
                            {"name": "max_tokens", "type": "integer", "description": "Maximum tokens in response (optional)"},
                            {"name": "stream", "type": "boolean", "description": "Enable streaming response (optional, default: false)"},
                            {"name": "system", "type": "string", "description": "System message for conversation context (optional)"},
                            {"name": "cache", "type": "boolean", "description": "Enable response caching (optional, default: true)"},
                        ],
                        "response": "LLM response with metadata including provider, model, response time, and cache status",
                    },
                    {
                        "method": "GET",
                        "path": "/llm/api/providers/status/",
                        "description": "Get status and health information for all configured LLM providers",
                        "parameters": [],
                        "response": "Array of provider objects with status, configuration, and availability info",
                    },
                    {
                        "method": "GET",
                        "path": "/llm/api/stats/",
                        "description": "Get comprehensive usage statistics and performance metrics",
                        "parameters": [
                            {"name": "period", "type": "string", "description": "Time period for stats (day, week, month, default: day)"},
                            {"name": "provider", "type": "string", "description": "Filter stats by specific provider (optional)"},
                            {"name": "application", "type": "string", "description": "Filter stats by application identifier (optional)"},
                        ],
                        "response": "Statistics including query counts, success rates, response times, cache performance, and provider breakdowns",
                    },
                ],
            },
        }

        context = {"api_endpoints": api_endpoints, "title": "NRC EWAS - API Documentation"}

        return render(request, "api_documentation.html", context)
