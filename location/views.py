"""Views for location management - both web interface and API."""

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from .forms import GazetteerForm, LocationForm
from .models import AdmLevel, Gazetteer, Location, UnmatchedLocation
from .utils import location_matcher

# =============================================================================
# WEB INTERFACE VIEWS
# =============================================================================


@login_required
def dashboard(request):
    """Dashboard view with location statistics."""
    stats = {
        "total_locations": Location.objects.count(),
        "total_admin_levels": AdmLevel.objects.count(),
        "total_gazetteer_entries": Gazetteer.objects.count(),
        "locations_by_admin_level": list(
            AdmLevel.objects.annotate(
                location_count=Count("locations"),
            )
            .values("name", "code", "location_count")
            .order_by("code")
        ),
        "recent_locations": Location.objects.select_related("admin_level", "parent").order_by("-created_at")[:5],
        "recent_gazetteer_entries": Gazetteer.objects.select_related("location", "location__admin_level").order_by("-id")[:5],
    }

    return render(request, "location/dashboard.html", {"stats": stats})


class LocationListView(LoginRequiredMixin, ListView):
    """List view for locations with search and filtering."""

    model = Location
    template_name = "location/location_list.html"
    context_object_name = "locations"
    paginate_by = 20

    def get_queryset(self):
        """Return the queryset for the list view."""
        queryset = Location.objects.select_related("admin_level", "parent")

        # Search functionality
        search = self.request.GET.get("search", "").strip()
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(geo_id__icontains=search) | Q(comment__icontains=search))

        # Filter by admin level
        admin_level = self.request.GET.get("admin_level")
        if admin_level:
            queryset = queryset.filter(admin_level__code=admin_level)

        # Filter by parent
        parent_id = self.request.GET.get("parent")
        if parent_id:
            queryset = queryset.filter(parent_id=parent_id)

        return queryset.order_by("geo_id")

    def get_context_data(self, **kwargs):
        """Return the context data for the list view."""
        context = super().get_context_data(**kwargs)
        context["admin_levels"] = AdmLevel.objects.all().order_by("code")
        context["search_query"] = self.request.GET.get("search", "")
        context["selected_admin_level"] = self.request.GET.get("admin_level", "")
        context["selected_parent"] = self.request.GET.get("parent", "")

        # Get parent locations for filter dropdown
        if self.request.GET.get("admin_level"):
            try:
                level_code = self.request.GET.get("admin_level")
                parent_level_code = str(int(level_code) - 1) if int(level_code) > 0 else None
                if parent_level_code is not None:
                    context["parent_locations"] = Location.objects.filter(admin_level__code=parent_level_code).order_by("name")
            except (ValueError, TypeError):
                pass

        return context


class LocationDetailView(LoginRequiredMixin, DetailView):
    """Detail view for a single location."""

    model = Location
    template_name = "location/location_detail.html"
    context_object_name = "location"

    def get_queryset(self):
        """Return the queryset for the detail view."""
        return Location.objects.select_related("admin_level", "parent")

    def get_context_data(self, **kwargs):
        """Return the context data for the detail view."""
        context = super().get_context_data(**kwargs)
        location = self.object

        context["hierarchy"] = location.get_full_hierarchy()
        context["children"] = location.children.select_related("admin_level").order_by("geo_id")
        context["gazetteer_entries"] = location.gazetteer_entries.all()

        return context


class LocationCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    """Create view for new locations."""

    model = Location
    form_class = LocationForm
    template_name = "location/location_form.html"
    success_message = "Location '%(name)s' was created successfully."

    def get_success_url(self):
        """Return the URL to redirect to after successful creation."""
        return reverse("location:location_detail", kwargs={"pk": self.object.pk})


class LocationUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    """Update view for existing locations."""

    model = Location
    form_class = LocationForm
    template_name = "location/location_form.html"
    success_message = "Location '%(name)s' was updated successfully."

    def get_success_url(self):
        """Return the URL to redirect to after successful update."""
        return reverse("location:location_detail", kwargs={"pk": self.object.pk})


class LocationDeleteView(LoginRequiredMixin, DeleteView):
    """Delete view for locations."""

    model = Location
    template_name = "location/location_confirm_delete.html"

    def get_success_url(self):
        """Return the URL to redirect to after successful deletion."""
        messages.success(self.request, f"Location '{self.object.name}' was deleted successfully.")
        return reverse("location:location_list")


class GazetteerListView(LoginRequiredMixin, ListView):
    """List view for gazetteer entries with search and filtering."""

    model = Gazetteer
    template_name = "location/gazetteer_list.html"
    context_object_name = "entries"
    paginate_by = 20

    def get_queryset(self):
        """Return the queryset for the list view."""
        queryset = Gazetteer.objects.select_related("location", "location__admin_level", "location__parent")

        # Search functionality
        search = self.request.GET.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(code__icontains=search) | Q(source__icontains=search) | Q(location__name__icontains=search) | Q(location__geo_id__icontains=search)
            )

        # Filter by source
        source = self.request.GET.get("source")
        if source:
            queryset = queryset.filter(source=source)

        # Filter by location's admin level
        admin_level = self.request.GET.get("admin_level")
        if admin_level:
            queryset = queryset.filter(location__admin_level__code=admin_level)

        return queryset.order_by("source", "name")

    def get_context_data(self, **kwargs):
        """Return the context data for the list view."""
        context = super().get_context_data(**kwargs)
        context["admin_levels"] = AdmLevel.objects.all().order_by("code")
        context["sources"] = Gazetteer.objects.values_list("source", flat=True).distinct().order_by("source")
        context["search_query"] = self.request.GET.get("search", "")
        context["selected_source"] = self.request.GET.get("source", "")
        context["selected_admin_level"] = self.request.GET.get("admin_level", "")

        return context


class GazetteerCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    """Create view for new gazetteer entries."""

    model = Gazetteer
    form_class = GazetteerForm
    template_name = "location/gazetteer_form.html"
    success_message = "Gazetteer entry for '%(name)s' was created successfully."

    def get_success_url(self):
        """Return the URL to redirect to after successful creation."""
        return reverse("location:gazetteer_list")


class GazetteerUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    """Update view for existing gazetteer entries."""

    model = Gazetteer
    form_class = GazetteerForm
    template_name = "location/gazetteer_form.html"
    success_message = "Gazetteer entry for '%(name)s' was updated successfully."

    def get_success_url(self):
        """Return the URL to redirect to after successful update."""
        return reverse("location:gazetteer_list")


class GazetteerDeleteView(LoginRequiredMixin, DeleteView):
    """Delete view for gazetteer entries."""

    model = Gazetteer
    template_name = "location/gazetteer_confirm_delete.html"

    def get_success_url(self):
        """Return the URL to redirect to after successful deletion."""
        messages.success(self.request, f"Gazetteer entry '{self.object.name}' was deleted successfully.")
        return reverse("location:gazetteer_list")


@login_required
def location_matcher_view(request):
    """Web interface for location matching functionality."""
    if request.method == "POST":
        location_name = request.POST.get("location_name", "").strip()
        source = request.POST.get("source", "").strip()
        admin_level = request.POST.get("admin_level")
        parent_id = request.POST.get("parent_id")

        if not location_name:
            messages.error(request, "Location name is required.")
        else:
            # Get parent location if specified
            parent_location = None
            if parent_id:
                try:
                    parent_location = Location.objects.get(id=parent_id)
                except Location.DoesNotExist:
                    messages.error(request, f"Parent location with id {parent_id} not found.")
                    return redirect("location:location_matcher")

            # Perform matching
            matched_location = location_matcher.match_location(
                location_name=location_name,
                source=source or None,
                admin_level=admin_level or None,
                parent_location=parent_location,
            )

            if matched_location:
                messages.success(request, f"Location '{location_name}' matched to '{matched_location.name}' ({matched_location.geo_id}).")
                return redirect("location:location_detail", pk=matched_location.pk)
            else:
                messages.warning(request, f"No exact match found for '{location_name}'. Consider adding it to the gazetteer manually.")

    context = {
        "admin_levels": AdmLevel.objects.all().order_by("code"),
        "sources": Gazetteer.objects.values_list("source", flat=True).distinct().order_by("source"),
        "locations": Location.objects.exclude(admin_level__code="3").select_related("admin_level").order_by("geo_id"),
    }

    return render(request, "location/location_matcher.html", context)


# =============================================================================
# API VIEWS (EXISTING)
# =============================================================================


@require_http_methods(["GET"])
@login_required
def locations_api(request):
    """API endpoint to list locations with filtering and pagination."""
    try:
        # Get query parameters
        admin_level = request.GET.get("admin_level")
        parent_id = request.GET.get("parent")
        search = request.GET.get("search", "").strip()
        page = int(request.GET.get("page", 1))
        page_size = min(int(request.GET.get("page_size", 50)), 1000)  # Max 1000 per page

        # Build query
        query = Q()

        if admin_level:
            query &= Q(admin_level__code=admin_level)

        if parent_id:
            query &= Q(parent_id=parent_id)

        if search:
            query &= Q(name__icontains=search) | Q(geo_id__icontains=search) | Q(comment__icontains=search)

        # Get locations
        locations = Location.objects.filter(query).select_related("admin_level", "parent").order_by("geo_id")

        # Paginate
        paginator = Paginator(locations, page_size)
        page_obj = paginator.get_page(page)

        # Serialize data
        data = []
        for location in page_obj:
            data.append(
                {
                    "id": location.id,
                    "geo_id": location.geo_id,
                    "name": location.name,
                    "admin_level": {"code": location.admin_level.code, "name": location.admin_level.name},
                    "parent": {"id": location.parent.id, "geo_id": location.parent.geo_id, "name": location.parent.name} if location.parent else None,
                    "has_children": location.children.exists(),
                    "point": {"coordinates": [location.point.x, location.point.y]} if location.point else None,
                    "created_at": location.created_at.isoformat(),
                    "updated_at": location.updated_at.isoformat(),
                }
            )

        return JsonResponse(
            {
                "success": True,
                "data": data,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total_pages": paginator.num_pages,
                    "total_count": paginator.count,
                    "has_next": page_obj.has_next(),
                    "has_previous": page_obj.has_previous(),
                },
            }
        )

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_http_methods(["GET"])
@login_required
def admin_levels_api(request):
    """API endpoint to list administrative levels."""
    try:
        admin_levels = AdmLevel.objects.all().order_by("code")

        data = []
        for level in admin_levels:
            data.append({"code": level.code, "name": level.name, "location_count": level.locations.count()})

        return JsonResponse({"success": True, "data": data})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def match_location_api(request):
    """API endpoint for location matching."""
    try:
        data = json.loads(request.body)

        location_name = data.get("location_name", "").strip()
        source = data.get("source")
        admin_level = data.get("admin_level")
        parent_id = data.get("parent_id")

        if not location_name:
            return JsonResponse({"success": False, "error": "location_name is required"}, status=400)

        # Get parent location if specified
        parent_location = None
        if parent_id:
            try:
                parent_location = Location.objects.get(id=parent_id)
            except Location.DoesNotExist:
                return JsonResponse({"success": False, "error": f"Parent location with id {parent_id} not found"}, status=400)

        # Perform matching
        matched_location = location_matcher.match_location(location_name=location_name, source=source, admin_level=admin_level, parent_location=parent_location)

        result = {"success": True, "query": {"location_name": location_name, "source": source, "admin_level": admin_level, "parent_id": parent_id}}

        if matched_location:
            result["match"] = {
                "id": matched_location.id,
                "geo_id": matched_location.geo_id,
                "name": matched_location.name,
                "admin_level": {"code": matched_location.admin_level.code, "name": matched_location.admin_level.name},
                "hierarchy": [{"id": loc.id, "geo_id": loc.geo_id, "name": loc.name, "admin_level": loc.admin_level.code} for loc in matched_location.get_full_hierarchy()],
            }
        else:
            result["match"] = None
            result["message"] = "No exact match found. Please add this location to the gazetteer manually."

        return JsonResponse(result)

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON in request body"}, status=400)

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def bulk_match_locations_api(request):
    """API endpoint for bulk location matching."""
    try:
        data = json.loads(request.body)

        location_names = data.get("location_names", [])
        source = data.get("source")
        admin_level = data.get("admin_level")
        parent_id = data.get("parent_id")

        if not location_names:
            return JsonResponse({"success": False, "error": "location_names array is required"}, status=400)

        if not isinstance(location_names, list):
            return JsonResponse({"success": False, "error": "location_names must be an array"}, status=400)

        # Get parent location if specified
        parent_location = None
        if parent_id:
            try:
                parent_location = Location.objects.get(id=parent_id)
            except Location.DoesNotExist:
                return JsonResponse({"success": False, "error": f"Parent location with id {parent_id} not found"}, status=400)

        # Perform bulk matching
        results = location_matcher.bulk_match_locations(location_names=location_names, source=source, admin_level=admin_level, parent_location=parent_location)

        # Serialize results
        serialized_results = {}
        for name, location in results.items():
            if location:
                serialized_results[name] = {
                    "id": location.id,
                    "geo_id": location.geo_id,
                    "name": location.name,
                    "admin_level": {"code": location.admin_level.code, "name": location.admin_level.name},
                }
            else:
                serialized_results[name] = None

        return JsonResponse(
            {
                "success": True,
                "query": {"location_names": location_names, "source": source, "admin_level": admin_level, "parent_id": parent_id},
                "results": serialized_results,
                "statistics": {
                    "total_queries": len(location_names),
                    "successful_matches": sum(1 for result in results.values() if result is not None),
                    "failed_matches": sum(1 for result in results.values() if result is None),
                },
            }
        )

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON in request body"}, status=400)

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_http_methods(["GET"])
@login_required
def location_hierarchy_api(request, location_id):
    """API endpoint to get location hierarchy."""
    try:
        location = Location.objects.select_related("admin_level").get(id=location_id)

        hierarchy = location.get_full_hierarchy()
        children = location.children.select_related("admin_level").all()

        result = {
            "success": True,
            "location": {
                "id": location.id,
                "geo_id": location.geo_id,
                "name": location.name,
                "admin_level": {"code": location.admin_level.code, "name": location.admin_level.name},
            },
            "hierarchy": [{"id": loc.id, "geo_id": loc.geo_id, "name": loc.name, "admin_level": {"code": loc.admin_level.code, "name": loc.admin_level.name}} for loc in hierarchy],
            "children": [
                {"id": child.id, "geo_id": child.geo_id, "name": child.name, "admin_level": {"code": child.admin_level.code, "name": child.admin_level.name}} for child in children
            ],
        }

        return JsonResponse(result)

    except Location.DoesNotExist:
        return JsonResponse({"success": False, "error": f"Location with id {location_id} not found"}, status=404)

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


# =============================================================================
# LOCATION BROWSER VIEWS
# =============================================================================


@login_required
def location_browser_view(request):
    """Location browsing interface with interactive map."""
    return render(request, "location/location_browser.html")


@require_http_methods(["GET"])
@login_required
def browser_locations_api(request):
    """API endpoint for location browser - returns locations with GeoJSON boundaries."""
    try:
        admin_level_code = request.GET.get("admin_level", "0")
        parent_id = request.GET.get("parent_id")

        query = Q(admin_level__code=admin_level_code)

        if parent_id:
            query &= Q(parent_id=parent_id)

        locations = Location.objects.filter(query).select_related("admin_level", "parent").prefetch_related("children").order_by("name")

        features = []
        for location in locations:
            properties = {
                "id": location.id,
                "geo_id": location.geo_id,
                "name": location.name,
                "admin_level": {"code": location.admin_level.code, "name": location.admin_level.name},
                "parent": {"id": location.parent.id, "name": location.parent.name, "geo_id": location.parent.geo_id} if location.parent else None,
                "has_children": location.children.exists(),
            }

            if location.boundary:
                feature = {"type": "Feature", "properties": properties, "geometry": json.loads(location.boundary.geojson)}
            elif location.point:
                feature = {"type": "Feature", "properties": properties, "geometry": json.loads(location.point.geojson)}
            else:
                feature = {"type": "Feature", "properties": properties, "geometry": None}

            features.append(feature)

        return JsonResponse({"success": True, "type": "FeatureCollection", "features": features})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_http_methods(["GET"])
@login_required
def browser_location_details_api(request, location_id):
    """API endpoint for detailed location information including hierarchy and alternate names."""
    try:
        location = Location.objects.select_related("admin_level", "parent").prefetch_related("children__admin_level", "gazetteer_entries").get(id=location_id)

        hierarchy = location.get_full_hierarchy()
        children = location.children.all().order_by("name")
        gazetteer_entries = location.gazetteer_entries.all()

        result = {
            "success": True,
            "location": {
                "id": location.id,
                "geo_id": location.geo_id,
                "name": location.name,
                "comment": location.comment,
                "admin_level": {"code": location.admin_level.code, "name": location.admin_level.name},
                "parent": {"id": location.parent.id, "name": location.parent.name, "geo_id": location.parent.geo_id} if location.parent else None,
                "centroid": {"coordinates": [location.point.x, location.point.y]} if location.point else None,
            },
            "hierarchy": [{"id": loc.id, "geo_id": loc.geo_id, "name": loc.name, "admin_level": {"code": loc.admin_level.code, "name": loc.admin_level.name}} for loc in hierarchy],
            "children": [
                {"id": child.id, "geo_id": child.geo_id, "name": child.name, "admin_level": {"code": child.admin_level.code, "name": child.admin_level.name}} for child in children
            ],
            "alternate_names": [{"id": entry.id, "name": entry.name, "code": entry.code, "source": entry.source} for entry in gazetteer_entries],
        }

        return JsonResponse(result)

    except Location.DoesNotExist:
        return JsonResponse({"success": False, "error": f"Location with id {location_id} not found"}, status=404)
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


# =============================================================================
# UNMATCHED LOCATIONS MANAGEMENT
# =============================================================================


def calculate_match_probability(unmatched_name: str, location: Location) -> float:
    """Calculate probability of match between unmatched name and location."""
    from difflib import SequenceMatcher

    unmatched_lower = unmatched_name.lower().strip()
    location_lower = location.name.lower().strip()

    # Direct similarity
    direct_similarity = SequenceMatcher(None, unmatched_lower, location_lower).ratio()

    # Check for substring matches
    if unmatched_lower in location_lower or location_lower in unmatched_lower:
        direct_similarity = max(direct_similarity, 0.7)

    # Handle "State" suffix variations
    unmatched_base = unmatched_lower.replace(" state", "")
    location_base = location_lower.replace(" state", "")

    if unmatched_base != unmatched_lower or location_base != location_lower:
        base_similarity = SequenceMatcher(None, unmatched_base, location_base).ratio()
        direct_similarity = max(direct_similarity, base_similarity * 0.9)

    # Check gazetteer entries for additional name variations
    gazetteer_similarity = 0.0
    for entry in location.gazetteer_entries.all():
        entry_lower = entry.name.lower().strip()
        entry_similarity = SequenceMatcher(None, unmatched_lower, entry_lower).ratio()
        gazetteer_similarity = max(gazetteer_similarity, entry_similarity)

    # Combine similarities with weights
    final_similarity = max(direct_similarity, gazetteer_similarity * 0.95)

    return min(final_similarity, 1.0)


@login_required
def unmatched_locations_view(request):
    """View for managing unmatched locations."""
    # Get filter parameters
    source_filter = request.GET.get("source", "")
    search_query = request.GET.get("search", "").strip()

    # Base queryset - only show unmatched locations (not yet matched)
    queryset = UnmatchedLocation.objects.filter(is_matched=False)

    # Apply filters
    if source_filter:
        queryset = queryset.filter(source=source_filter)

    if search_query:
        queryset = queryset.filter(Q(name__icontains=search_query) | Q(context__icontains=search_query) | Q(notes__icontains=search_query))

    # Order by occurrence count and last seen
    unmatched_locations = queryset.order_by("-occurrence_count", "-last_seen")

    # Paginate
    paginator = Paginator(unmatched_locations, 20)
    page = request.GET.get("page", 1)
    page_obj = paginator.get_page(page)

    # Use precomputed potential matches for performance
    locations_with_matches = []

    for unmatched in page_obj:
        # Get precomputed potential matches
        precomputed_matches = unmatched.potential_matches or []
        potential_matches = []

        # Convert precomputed matches to the format expected by the template
        for match_data in precomputed_matches:
            try:
                location = Location.objects.select_related("admin_level").get(id=match_data["location_id"])
                potential_matches.append(
                    {
                        "location": location,
                        "probability": match_data["similarity_score"],
                        "matched_name": match_data.get("matched_name", location.name),
                        "match_source": match_data.get("match_source", "primary"),
                    }
                )
            except Location.DoesNotExist:
                # Skip if location was deleted after computation
                continue

        # If no precomputed matches are available, trigger computation and show empty for now
        if not potential_matches and not unmatched.potential_matches_computed_at:
            # Trigger background computation
            unmatched.trigger_match_computation()

        locations_with_matches.append({"unmatched": unmatched, "potential_matches": potential_matches, "computation_pending": not unmatched.potential_matches_computed_at})

    # Get filter options
    sources = UnmatchedLocation.objects.values_list("source", flat=True).distinct()

    context = {
        "locations_with_matches": locations_with_matches,
        "page_obj": page_obj,
        "sources": sorted(sources),
        "source_filter": source_filter,
        "search_query": search_query,
    }

    return render(request, "location/unmatched_locations.html", context)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def add_to_gazetteer_ajax(request):
    """AJAX endpoint to add unmatched location to gazetteer."""
    try:
        data = json.loads(request.body)
        unmatched_id = data.get("unmatched_id")
        location_id = data.get("location_id")

        if not unmatched_id or not location_id:
            return JsonResponse({"success": False, "error": "Both unmatched_id and location_id are required"}, status=400)

        # Get the unmatched location and target location
        unmatched = UnmatchedLocation.objects.get(id=unmatched_id)
        location = Location.objects.get(id=location_id)

        # Create gazetteer entry - check for existing entries to avoid constraint violations
        try:
            # Check if a gazetteer entry already exists with the same location, source, and name
            existing_by_name = Gazetteer.objects.filter(location=location, source=unmatched.source, name=unmatched.name).first()

            # Check if a gazetteer entry already exists with the same location, source, and code
            # Include empty/blank codes in the check
            code_to_check = unmatched.code or ""
            existing_by_code = Gazetteer.objects.filter(location=location, source=unmatched.source, code=code_to_check).first()

            if existing_by_name:
                gazetteer = existing_by_name
                created = False
            elif existing_by_code:
                gazetteer = existing_by_code
                created = False
            else:
                # No existing entry found, create new one
                gazetteer = Gazetteer.objects.create(location=location, name=unmatched.name, source=unmatched.source, code=code_to_check)
                created = True
        except Exception as e:
            return JsonResponse({"success": False, "error": f"Database error: {str(e)}"}, status=500)

        # Update unmatched location with matching info
        from django.utils import timezone

        unmatched.resolved_location = location
        unmatched.is_matched = True
        unmatched.matched_at = timezone.now()
        unmatched.matched_by = request.user
        unmatched.notes = f"Resolved by {request.user.username}"
        unmatched.save()

        # Trigger pipeline API update
        try:
            from .pipeline_integration import PipelineAPIError, trigger_single_location_update

            api_result = trigger_single_location_update(unmatched_id)
            pipeline_message = api_result.get("message", "Pipeline update triggered")
        except PipelineAPIError as e:
            # Log the error but don't fail the operation
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Pipeline API error for unmatched location {unmatched_id}: {str(e)}")
            pipeline_message = f"Warning: {str(e)}"
        except Exception as e:
            # Log unexpected errors but don't fail
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Unexpected error calling pipeline API for unmatched location {unmatched_id}: {str(e)}")
            pipeline_message = "Warning: Pipeline update failed"

        if created:
            return JsonResponse(
                {
                    "success": True,
                    "message": f'Successfully added "{unmatched.name}" to gazetteer for location "{location.name}". {pipeline_message}',
                    "gazetteer_id": gazetteer.id,
                    "location_name": location.name,
                    "unmatched_id": unmatched_id,
                }
            )
        else:
            return JsonResponse(
                {
                    "success": True,
                    "message": f'"{unmatched.name}" was already in gazetteer for location "{location.name}" - marked as resolved. {pipeline_message}',
                    "gazetteer_id": gazetteer.id,
                    "location_name": location.name,
                    "unmatched_id": unmatched_id,
                }
            )

    except UnmatchedLocation.DoesNotExist:
        return JsonResponse({"success": False, "error": "Unmatched location not found"}, status=404)
    except Location.DoesNotExist:
        return JsonResponse({"success": False, "error": "Location not found"}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def delete_unmatched_ajax(request):
    """AJAX endpoint to delete an unmatched location."""
    try:
        data = json.loads(request.body)
        unmatched_id = data.get("unmatched_id")

        if not unmatched_id:
            return JsonResponse({"success": False, "error": "unmatched_id is required"}, status=400)

        # Get and delete the unmatched location
        unmatched = UnmatchedLocation.objects.get(id=unmatched_id)
        unmatched_name = unmatched.name
        unmatched.delete()

        return JsonResponse({"success": True, "message": f'Successfully deleted unmatched location "{unmatched_name}"'})

    except UnmatchedLocation.DoesNotExist:
        return JsonResponse({"success": False, "error": "Unmatched location not found"}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
@login_required
def location_search_api(request):
    """AJAX API endpoint to search for locations by name for manual matching.

    This provides a fast search interface when the precomputed matches
    don't contain the desired location.
    """
    try:
        query = request.GET.get("q", "").strip()
        limit = min(int(request.GET.get("limit", 20)), 100)  # Max 100 results

        if not query or len(query) < 2:
            return JsonResponse({"success": True, "results": [], "message": "Query must be at least 2 characters"})

        # Search in locations and gazetteer entries
        results = []

        # Search locations by name (both English and Arabic)
        location_queries = Q(name__icontains=query)
        if hasattr(Location, "name_ar"):
            location_queries |= Q(name_ar__icontains=query)

        locations = Location.objects.filter(location_queries).select_related("admin_level", "parent").order_by("name")[:limit]

        for location in locations:
            # Build hierarchy path for context
            hierarchy = location.get_full_hierarchy()
            hierarchy_text = " > ".join([loc.name for loc in hierarchy])

            results.append(
                {
                    "id": location.id,
                    "geo_id": location.geo_id,
                    "name": location.name,
                    "name_ar": getattr(location, "name_ar", ""),
                    "admin_level": {"code": location.admin_level.code, "name": location.admin_level.name},
                    "hierarchy_text": hierarchy_text,
                    "match_type": "location_name",
                }
            )

        # Also search gazetteer entries if we haven't reached limit
        if len(results) < limit:
            remaining_limit = limit - len(results)
            gazetteer_entries = (
                Gazetteer.objects.filter(name__icontains=query)
                .select_related("location", "location__admin_level", "location__parent")
                .exclude(
                    location__in=[r["id"] for r in results]  # Avoid duplicates
                )[:remaining_limit]
            )

            for entry in gazetteer_entries:
                location = entry.location
                hierarchy = location.get_full_hierarchy()
                hierarchy_text = " > ".join([loc.name for loc in hierarchy])

                results.append(
                    {
                        "id": location.id,
                        "geo_id": location.geo_id,
                        "name": location.name,
                        "name_ar": getattr(location, "name_ar", ""),
                        "admin_level": {"code": location.admin_level.code, "name": location.admin_level.name},
                        "hierarchy_text": hierarchy_text,
                        "match_type": "gazetteer_alias",
                        "matched_name": entry.name,  # The gazetteer name that matched
                        "source": entry.source,
                    }
                )

        return JsonResponse({"success": True, "results": results, "query": query, "total_found": len(results)})

    except ValueError:
        return JsonResponse({"success": False, "error": "Invalid limit parameter"}, status=400)
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)
