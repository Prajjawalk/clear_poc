"""Data pipeline management views and API endpoints."""

import logging
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Max, Min, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .forms import SourceForm, VariableForm
from .models import Source, TaskStatistics, Variable, VariableData

logger = logging.getLogger(__name__)


@login_required
def dashboard(request):
    """Main dashboard for data pipeline management."""
    try:
        # Get summary statistics
        total_sources = Source.objects.count()
        total_variables = Variable.objects.count()
        total_data_records = VariableData.objects.count()

        # Recent data statistics
        last_week = timezone.now() - timedelta(days=7)
        recent_data_count = VariableData.objects.filter(
            created_at__gte=last_week
        ).count()

        # Source statistics - use distinct count to avoid Cartesian product issues
        sources_with_stats = Source.objects.annotate(
            variable_count=Count('variables', distinct=True),
            data_count=Count('variables__data_records', distinct=True)
        ).order_by('-variable_count')[:5]

        # Variable statistics
        variables_with_stats = Variable.objects.annotate(
            data_count=Count('data_records')
        ).order_by('-data_count')[:5]

        # Recent task statistics
        recent_stats = TaskStatistics.objects.order_by('-date')[:7]

        context = {
            'total_sources': total_sources,
            'total_variables': total_variables,
            'total_data_records': total_data_records,
            'recent_data_count': recent_data_count,
            'top_sources': sources_with_stats,
            'top_variables': variables_with_stats,
            'recent_task_stats': recent_stats,
        }

    except Exception as e:
        # Handle database connection errors gracefully
        context = {
            'total_sources': 0,
            'total_variables': 0,
            'total_data_records': 0,
            'recent_data_count': 0,
            'top_sources': [],
            'top_variables': [],
            'recent_task_stats': [],
            'db_error': str(e),
        }

    return render(request, 'data_pipeline/dashboard.html', context)


@login_required
def source_list(request):
    """List all data sources with search and filtering."""
    query = request.GET.get('q', '')
    source_type = request.GET.get('type', '')

    sources = Source.objects.annotate(
        variable_count=Count('variables', distinct=True),
        data_count=Count('variables__data_records', distinct=True)
    )

    if query:
        sources = sources.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(class_name__icontains=query)
        )

    if source_type:
        sources = sources.filter(type=source_type)

    # Pagination
    paginator = Paginator(sources, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Get distinct source types for filter
    source_types = Source.objects.values_list('type', flat=True).distinct()

    context = {
        'page_obj': page_obj,
        'query': query,
        'source_type': source_type,
        'source_types': source_types,
        'total_count': sources.count(),
    }

    return render(request, 'data_pipeline/source_list.html', context)


@login_required
def source_detail(request, source_id):
    """Detailed view of a specific source."""
    source = get_object_or_404(Source, id=source_id)

    # Get variables for this source with statistics
    variables = source.variables.annotate(
        data_count=Count('data_records'),
        latest_data=Max('data_records__end_date')
    ).order_by('name')

    # Get recent data records
    recent_data = VariableData.objects.filter(
        variable__source=source
    ).select_related('variable', 'gid', 'adm_level').order_by('-created_at')[:10]

    # Statistics for this source
    total_variables = variables.count()
    total_data_records = VariableData.objects.filter(variable__source=source).count()

    context = {
        'source': source,
        'variables': variables,
        'recent_data': recent_data,
        'total_variables': total_variables,
        'total_data_records': total_data_records,
    }

    return render(request, 'data_pipeline/source_detail.html', context)


@login_required
def source_create(request):
    """Create a new data source."""
    if request.method == 'POST':
        form = SourceForm(request.POST)
        if form.is_valid():
            source = form.save()
            messages.success(request, f'Source "{source.name}" created successfully.')
            return redirect('data_pipeline:source_detail', source_id=source.id)
    else:
        form = SourceForm()

    context = {
        'form': form,
        'action': 'Create',
        'submit_text': 'Create Source',
    }

    return render(request, 'data_pipeline/source_form.html', context)


@login_required
def source_edit(request, source_id):
    """Edit an existing data source."""
    source = get_object_or_404(Source, id=source_id)

    if request.method == 'POST':
        form = SourceForm(request.POST, instance=source)
        if form.is_valid():
            source = form.save()
            messages.success(request, f'Source "{source.name}" updated successfully.')
            return redirect('data_pipeline:source_detail', source_id=source.id)
    else:
        form = SourceForm(instance=source)

    context = {
        'form': form,
        'source': source,
        'action': 'Edit',
        'submit_text': 'Update Source',
    }

    return render(request, 'data_pipeline/source_form.html', context)


@login_required
def source_delete(request, source_id):
    """Delete a data source."""
    source = get_object_or_404(Source, id=source_id)

    if request.method == 'POST':
        source_name = source.name
        source.delete()
        messages.success(request, f'Source "{source_name}" deleted successfully.')
        return redirect('data_pipeline:source_list')

    # Get related objects that will be deleted
    variables_count = source.variables.count()
    data_count = VariableData.objects.filter(variable__source=source).count()

    context = {
        'source': source,
        'variables_count': variables_count,
        'data_count': data_count,
    }

    return render(request, 'data_pipeline/source_confirm_delete.html', context)


@login_required
def variable_list(request):
    """List all variables with search and filtering."""
    query = request.GET.get('q', '')
    source_id = request.GET.get('source', '')
    var_type = request.GET.get('type', '')
    period = request.GET.get('period', '')

    variables = Variable.objects.select_related('source').annotate(
        data_count=Count('data_records'),
        latest_data=Max('data_records__end_date')
    )

    if query:
        variables = variables.filter(
            Q(name__icontains=query) |
            Q(code__icontains=query) |
            Q(text__icontains=query) |
            Q(source__name__icontains=query)
        )

    if source_id:
        variables = variables.filter(source_id=source_id)

    if var_type:
        variables = variables.filter(type=var_type)

    if period:
        variables = variables.filter(period=period)

    # Pagination
    paginator = Paginator(variables, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Get filter options
    sources = Source.objects.all().order_by('name')
    variable_types = Variable.objects.values_list('type', flat=True).distinct()
    periods = Variable.objects.values_list('period', flat=True).distinct()

    context = {
        'page_obj': page_obj,
        'query': query,
        'selected_source': source_id,
        'selected_type': var_type,
        'selected_period': period,
        'sources': sources,
        'variable_types': variable_types,
        'periods': periods,
        'total_count': variables.count(),
    }

    return render(request, 'data_pipeline/variable_list.html', context)


@login_required
def variable_detail(request, variable_id):
    """Detailed view of a specific variable."""
    variable = get_object_or_404(Variable.objects.select_related('source'), id=variable_id)

    # Get recent data for this variable
    data_records = variable.data_records.select_related(
        'gid', 'adm_level'
    ).order_by('-end_date')

    # Pagination for data records
    paginator = Paginator(data_records, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Statistics
    total_records = data_records.count()
    date_range = data_records.aggregate(
        earliest=Min('start_date'),
        latest=Max('end_date')
    )

    # Data summary statistics (for quantitative variables)
    if variable.type == 'quantitative':
        value_stats = data_records.filter(value__isnull=False).aggregate(
            min_value=Min('value'),
            max_value=Max('value'),
            avg_value=Avg('value'),
            sum_value=Sum('value')
        )
    else:
        value_stats = None

    context = {
        'variable': variable,
        'page_obj': page_obj,
        'total_records': total_records,
        'date_range': date_range,
        'value_stats': value_stats,
    }

    return render(request, 'data_pipeline/variable_detail.html', context)


@login_required
def variable_create(request):
    """Create a new variable."""
    source_id = request.GET.get('source')

    if request.method == 'POST':
        form = VariableForm(request.POST)
        if form.is_valid():
            variable = form.save()
            messages.success(request, f'Variable "{variable.name}" created successfully.')
            return redirect('data_pipeline:variable_detail', variable_id=variable.id)
    else:
        # Pre-select source if provided
        initial = {}
        if source_id:
            initial['source'] = source_id
        form = VariableForm(initial=initial)

    context = {
        'form': form,
        'action': 'Create',
        'submit_text': 'Create Variable',
    }

    return render(request, 'data_pipeline/variable_form.html', context)


@login_required
def variable_edit(request, variable_id):
    """Edit an existing variable."""
    variable = get_object_or_404(Variable, id=variable_id)

    if request.method == 'POST':
        form = VariableForm(request.POST, instance=variable)
        if form.is_valid():
            variable = form.save()
            messages.success(request, f'Variable "{variable.name}" updated successfully.')
            return redirect('data_pipeline:variable_detail', variable_id=variable.id)
    else:
        form = VariableForm(instance=variable)

    context = {
        'form': form,
        'variable': variable,
        'action': 'Edit',
        'submit_text': 'Update Variable',
    }

    return render(request, 'data_pipeline/variable_form.html', context)


@login_required
def variable_delete(request, variable_id):
    """Delete a variable."""
    variable = get_object_or_404(Variable, id=variable_id)

    if request.method == 'POST':
        variable_name = variable.name
        source = variable.source
        variable.delete()
        messages.success(request, f'Variable "{variable_name}" deleted successfully.')
        return redirect('data_pipeline:source_detail', source_id=source.id)

    # Get related data that will be deleted
    data_count = variable.data_records.count()

    context = {
        'variable': variable,
        'data_count': data_count,
    }

    return render(request, 'data_pipeline/variable_confirm_delete.html', context)


# API Endpoints

@login_required
@require_http_methods(["GET"])
def sources_api(request):
    """API endpoint to list sources with statistics."""
    try:
        sources = Source.objects.annotate(
            variable_count=Count('variables'),
            data_count=Count('variables__data_records')
        ).order_by('name')

        data = []
        for source in sources:
            data.append({
                'id': source.id,
                'name': source.name,
                'description': source.description,
                'type': source.type,
                'info_url': source.info_url,
                'base_url': source.base_url,
                'class_name': source.class_name,
                'variable_count': source.variable_count,
                'data_count': source.data_count,
                'created_at': source.created_at.isoformat(),
                'updated_at': source.updated_at.isoformat()
            })

        return JsonResponse({
            'success': True,
            'data': data
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def variables_api(request):
    """API endpoint to list variables with filtering."""
    try:
        source_id = request.GET.get('source')

        variables = Variable.objects.select_related('source').annotate(
            data_count=Count('data_records')
        )

        if source_id:
            variables = variables.filter(source_id=source_id)

        variables = variables.order_by('source__name', 'name')

        data = []
        for variable in variables:
            data.append({
                'id': variable.id,
                'name': variable.name,
                'code': variable.code,
                'source': {
                    'id': variable.source.id,
                    'name': variable.source.name
                },
                'period': variable.period,
                'adm_level': variable.adm_level,
                'type': variable.type,
                'text': variable.text,
                'data_count': variable.data_count,
                'created_at': variable.created_at.isoformat(),
                'updated_at': variable.updated_at.isoformat()
            })

        return JsonResponse({
            'success': True,
            'data': data
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def data_api(request):
    """API endpoint to query variable data with filtering."""
    try:
        # Get query parameters
        variable_id = request.GET.get('variable')
        source_id = request.GET.get('source')
        location_id = request.GET.get('location')
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        page = int(request.GET.get('page', 1))
        page_size = min(int(request.GET.get('page_size', 50)), 1000)

        # Build query
        query = Q()

        if variable_id:
            query &= Q(variable_id=variable_id)

        if source_id:
            query &= Q(variable__source_id=source_id)

        if location_id:
            query &= Q(gid_id=location_id)

        if start_date:
            query &= Q(start_date__gte=datetime.fromisoformat(start_date.replace('Z', '+00:00')).date())

        if end_date:
            query &= Q(end_date__lte=datetime.fromisoformat(end_date.replace('Z', '+00:00')).date())

        # Get data records
        data_records = VariableData.objects.filter(query).select_related(
            'variable', 'variable__source', 'gid', 'adm_level'
        ).order_by('-end_date')

        # Paginate
        paginator = Paginator(data_records, page_size)
        page_obj = paginator.get_page(page)

        # Serialize data
        data = []
        for record in page_obj:
            data.append({
                'id': record.id,
                'variable': {
                    'id': record.variable.id,
                    'name': record.variable.name,
                    'code': record.variable.code,
                    'source': record.variable.source.name
                },
                'start_date': record.start_date.isoformat(),
                'end_date': record.end_date.isoformat(),
                'period': record.period,
                'location': {
                    'id': record.gid.id,
                    'geo_id': record.gid.geo_id,
                    'name': record.gid.name,
                    'admin_level': record.adm_level.name
                },
                'value': record.value,
                'text': record.text,
                'created_at': record.created_at.isoformat(),
                'updated_at': record.updated_at.isoformat()
            })

        return JsonResponse({
            'success': True,
            'data': data,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_pages': paginator.num_pages,
                'total_count': paginator.count,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous()
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def statistics_api(request):
    """API endpoint for pipeline statistics."""
    try:
        # Get date range from query parameters
        days = int(request.GET.get('days', 30))
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days)

        # Overall statistics
        total_sources = Source.objects.count()
        total_variables = Variable.objects.count()
        total_data_records = VariableData.objects.count()

        # Recent data statistics
        recent_data = VariableData.objects.filter(
            created_at__gte=timezone.now() - timedelta(days=days)
        )
        recent_count = recent_data.count()

        # Statistics by source
        source_stats = {}
        for source in Source.objects.annotate(variable_count=Count('variables')):
            data_count = VariableData.objects.filter(variable__source=source).count()
            source_stats[source.name] = {
                'variables': source.variable_count,
                'data_records': data_count
            }

        # Statistics by variable type
        type_stats = {}
        for var_type in Variable.TYPE_CHOICES:
            type_code = var_type[0]
            type_name = var_type[1]
            variable_count = Variable.objects.filter(type=type_code).count()
            data_count = VariableData.objects.filter(variable__type=type_code).count()

            type_stats[type_name] = {
                'variables': variable_count,
                'data_records': data_count
            }

        # Task statistics for the period
        task_stats = TaskStatistics.objects.filter(
            date__gte=start_date,
            date__lte=end_date
        ).aggregate(
            total_tasks=Sum('check_updates_count') + Sum('download_data_count') +
                       Sum('process_data_count') + Sum('full_pipeline_count') +
                       Sum('reprocess_data_count'),
            total_success=Sum('success_count'),
            total_failures=Sum('failure_count'),
            avg_duration=Avg('avg_duration_seconds')
        )

        return JsonResponse({
            'success': True,
            'period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'days': days
            },
            'overall': {
                'total_sources': total_sources,
                'total_variables': total_variables,
                'total_data_records': total_data_records,
                'recent_data_count': recent_count
            },
            'by_source': source_stats,
            'by_type': type_stats,
            'tasks': task_stats
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def map_data_api(request):
    """API endpoint for map data with geographic locations."""
    try:
        # Get query parameters
        source_id = request.GET.get('source')
        variable_id = request.GET.get('variable')
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        aggregation = request.GET.get('aggregation', 'latest')  # latest, sum, avg, count

        # Build query
        query = Q()

        if source_id:
            query &= Q(variable__source_id=source_id)

        if variable_id:
            query &= Q(variable_id=variable_id)

        if start_date:
            query &= Q(start_date__gte=datetime.fromisoformat(start_date.replace('Z', '+00:00')).date())

        if end_date:
            query &= Q(end_date__lte=datetime.fromisoformat(end_date.replace('Z', '+00:00')).date())

        # Get data records with location information
        data_records = VariableData.objects.filter(query).select_related(
            'variable', 'variable__source', 'gid', 'adm_level'
        ).exclude(
            gid__isnull=True
        ).order_by('-end_date')

        # Group by location for aggregation
        from collections import defaultdict
        location_data = defaultdict(list)

        for record in data_records:
            if record.gid and record.gid.latitude and record.gid.longitude:
                location_key = (record.gid.id, record.variable.id)
                location_data[location_key].append(record)

        # Process aggregated data
        map_features = []
        for (location_id, variable_id), records in location_data.items():
            if not records:
                continue

            location = records[0].gid
            variable = records[0].variable

            # Apply aggregation
            if aggregation == 'latest':
                # Most recent record
                record = records[0]
                aggregated_value = record.value
                record_count = 1
            elif aggregation == 'sum':
                # Sum all values
                if variable.type == 'quantitative':
                    numeric_records = [r for r in records if isinstance(r.value, (int, float))]
                    aggregated_value = sum(r.value for r in numeric_records) if numeric_records else 0
                    record_count = len(numeric_records)
                else:
                    aggregated_value = len(records)
                    record_count = len(records)
            elif aggregation == 'avg':
                # Average of values
                if variable.type == 'quantitative':
                    numeric_records = [r for r in records if isinstance(r.value, (int, float))]
                    aggregated_value = sum(r.value for r in numeric_records) / len(numeric_records) if numeric_records else 0
                    record_count = len(numeric_records)
                else:
                    aggregated_value = len(records)
                    record_count = len(records)
            else:  # count
                aggregated_value = len(records)
                record_count = len(records)

            # Create GeoJSON feature
            feature = {
                'type': 'Feature',
                'geometry': {
                    'type': 'Point',
                    'coordinates': [float(location.longitude), float(location.latitude)]
                },
                'properties': {
                    'location_id': location.id,
                    'location_name': location.name,
                    'geo_id': location.geo_id,
                    'admin_level': location.admin_level.code if location.admin_level else None,
                    'variable_id': variable.id,
                    'variable_name': variable.name,
                    'variable_code': variable.code,
                    'source_name': variable.source.name,
                    'value': aggregated_value,
                    'record_count': record_count,
                    'aggregation': aggregation,
                    'latest_date': records[0].end_date.isoformat(),
                    'earliest_date': records[-1].start_date.isoformat() if records else None,
                    'unit': variable.unit or '',
                    'type': variable.type
                }
            }

            map_features.append(feature)

        # Create GeoJSON response
        geojson = {
            'type': 'FeatureCollection',
            'features': map_features
        }

        return JsonResponse({
            'success': True,
            'data': geojson,
            'total_features': len(map_features),
            'filters': {
                'source_id': source_id,
                'variable_id': variable_id,
                'start_date': start_date,
                'end_date': end_date,
                'aggregation': aggregation
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def remove_source_data(request, source_id):
    """Remove all data for a specific source."""
    source = get_object_or_404(Source, id=source_id)

    try:
        # Count data records before deletion
        data_count = VariableData.objects.filter(variable__source=source).count()

        if data_count == 0:
            messages.info(request, f"No data records found for source '{source.name}'.")
        else:
            # Delete all data for this source
            deleted_count, _ = VariableData.objects.filter(variable__source=source).delete()
            messages.success(
                request,
                f"Successfully removed {deleted_count:,} data records from source '{source.name}'."
            )

        return redirect('data_pipeline:source_detail', source_id=source.id)

    except Exception as e:
        messages.error(
            request,
            f"Error removing data for source '{source.name}': {str(e)}"
        )
        return redirect('data_pipeline:source_detail', source_id=source.id)


@login_required
@require_http_methods(["POST"])
def remove_variable_data(request, variable_id):
    """Remove all data for a specific variable."""
    variable = get_object_or_404(Variable, id=variable_id)

    try:
        # Count data records before deletion
        data_count = variable.data_records.count()

        if data_count == 0:
            messages.info(request, f"No data records found for variable '{variable.name}'.")
        else:
            # Delete all data for this variable
            deleted_count, _ = variable.data_records.all().delete()
            messages.success(
                request,
                f"Successfully removed {deleted_count:,} data records from variable '{variable.name}'."
            )

        return redirect('data_pipeline:variable_detail', variable_id=variable.id)

    except Exception as e:
        messages.error(
            request,
            f"Error removing data for variable '{variable.name}': {str(e)}"
        )
        return redirect('data_pipeline:variable_detail', variable_id=variable.id)



@login_required
@require_http_methods(["POST"])
def trigger_variable_retrieval(request, variable_id):
    """Trigger data retrieval for a specific variable."""
    import os

    from .tasks import process_data, retrieve_data

    variable = get_object_or_404(Variable.objects.select_related('source'), id=variable_id)

    # Check for required environment variables based on source
    if variable.source.class_name == "IDMC" and not os.getenv('IDMC_API_KEY'):
        messages.error(request, "IDMC_API_KEY environment variable not set. Please configure it before running data retrieval.")
        return redirect('data_pipeline:variable_detail', variable_id=variable.id)

    if variable.source.class_name == "IOM":
        if not os.getenv('IOM_API_KEY'):
            messages.error(request, "IOM_API_KEY environment variable not set. Please configure it before running data retrieval.")
            return redirect('data_pipeline:variable_detail', variable_id=variable.id)
        if not os.getenv('IOM_APP'):
            messages.error(request, "IOM_APP environment variable not set. Please configure it before running data retrieval.")
            return redirect('data_pipeline:variable_detail', variable_id=variable.id)

    try:
        # Check if async processing is available
        use_async = request.POST.get('async', 'false') == 'true'

        if use_async:
            # Queue the retrieval task asynchronously
            result = retrieve_data.delay(variable.source.id, variable.id)
            # Also queue the processing task to run after retrieval
            process_result = process_data.apply_async(
                args=[variable.source.id, variable.id],
                countdown=10  # Wait 10 seconds before processing
            )
            messages.success(
                request,
                f"Data retrieval for '{variable.name}' has been queued. Task IDs: {result.id}, {process_result.id}"
            )
        else:
            # Run synchronously
            result = retrieve_data.apply(args=[variable.source.id, variable.id])

            if result.result and result.result.get("successful_retrievals", 0) > 0:
                # If retrieval was successful, also process the data
                process_result = process_data.apply(args=[variable.source.id, variable.id])

                messages.success(
                    request,
                    f"Successfully retrieved and processed data for '{variable.name}'"
                )
            else:
                error_msg = "Data retrieval failed"
                if result.result and "error" in result.result:
                    error_msg += f": {result.result['error']}"
                elif result.result and "variables" in result.result:
                    var_result = result.result["variables"].get(variable.code, {})
                    if "error" in var_result:
                        error_msg += f": {var_result['error']}"

                messages.error(request, error_msg)

        return redirect('data_pipeline:variable_detail', variable_id=variable.id)

    except Exception as e:
        messages.error(
            request,
            f"Error triggering data retrieval for '{variable.name}': {str(e)}"
        )
        return redirect('data_pipeline:variable_detail', variable_id=variable.id)


@require_http_methods(["POST"])
@login_required
def trigger_source_retrieval(request, source_id):
    """Trigger data retrieval for all variables of a specific source."""
    import os
    from .tasks import process_data, retrieve_data
    
    source = get_object_or_404(Source, id=source_id)
    variables = Variable.objects.filter(source=source)
    
    if not variables.exists():
        messages.error(request, f"No variables found for source '{source.name}'. Please add variables first.")
        return redirect('data_pipeline:source_detail', source_id=source.id)
    
    # Check for required environment variables based on source
    if source.class_name == "IDMC" and not os.getenv('IDMC_API_KEY'):
        messages.error(request, "IDMC_API_KEY environment variable not set. Please configure it before running data retrieval.")
        return redirect('data_pipeline:source_detail', source_id=source.id)
    
    if source.class_name == "IOM":
        if not os.getenv('IOM_API_KEY'):
            messages.error(request, "IOM_API_KEY environment variable not set. Please configure it before running data retrieval.")
            return redirect('data_pipeline:source_detail', source_id=source.id)
        if not os.getenv('IOM_APP'):
            messages.error(request, "IOM_APP environment variable not set. Please configure it before running data retrieval.")
            return redirect('data_pipeline:source_detail', source_id=source.id)
    
    try:
        # Check if async processing is available
        use_async = request.POST.get('async', 'false') == 'true'
        variable_count = variables.count()
        
        successful_retrievals = 0
        failed_retrievals = 0
        task_ids = []
        
        for variable in variables:
            try:
                if use_async:
                    # Queue the retrieval task asynchronously
                    result = retrieve_data.delay(source.id, variable.id)
                    # Also queue the processing task to run after retrieval
                    process_result = process_data.apply_async(
                        args=[source.id, variable.id],
                        countdown=10  # Wait 10 seconds before processing
                    )
                    task_ids.extend([result.id, process_result.id])
                    successful_retrievals += 1
                else:
                    # Run synchronously
                    result = retrieve_data.apply(args=[source.id, variable.id])
                    if result.result and result.result.get("successful_retrievals", 0) > 0:
                        # If retrieval was successful, also process the data
                        process_result = process_data.apply(args=[source.id, variable.id])
                        successful_retrievals += 1
                    else:
                        failed_retrievals += 1
                        
            except Exception as e:
                failed_retrievals += 1
                # Continue with other variables even if one fails
                continue
        
        # Provide feedback based on results
        if use_async:
            messages.success(
                request,
                f"Data retrieval for {variable_count} variable{'s' if variable_count != 1 else ''} from '{source.name}' has been queued. "
                f"Task IDs: {', '.join(task_ids[:10])}{'...' if len(task_ids) > 10 else ''}"
            )
        else:
            if successful_retrievals > 0 and failed_retrievals == 0:
                messages.success(
                    request,
                    f"Successfully retrieved and processed data for all {successful_retrievals} variable{'s' if successful_retrievals != 1 else ''} from '{source.name}'"
                )
            elif successful_retrievals > 0 and failed_retrievals > 0:
                messages.warning(
                    request,
                    f"Partially successful: {successful_retrievals} variable{'s' if successful_retrievals != 1 else ''} retrieved successfully, "
                    f"{failed_retrievals} failed from '{source.name}'"
                )
            else:
                messages.error(
                    request,
                    f"Data retrieval failed for all {variable_count} variable{'s' if variable_count != 1 else ''} from '{source.name}'"
                )
        
        return redirect('data_pipeline:source_detail', source_id=source.id)
        
    except Exception as e:
        messages.error(
            request,
            f"Error triggering data retrieval for source '{source.name}': {str(e)}"
        )
        return redirect('data_pipeline:source_detail', source_id=source.id)


@require_http_methods(["POST"])
@login_required
def trigger_source_retrieval_all(request, source_id):
    """Trigger data retrieval for all variables of a specific source using single API call."""
    import os
    from .tasks import full_source_pipeline
    
    logger.info(f"TRIGGER_SOURCE_RETRIEVAL_ALL: User {request.user.username} triggered retrieval for source_id={source_id}")
    
    source = get_object_or_404(Source, id=source_id)
    variables = Variable.objects.filter(source=source)
    
    logger.info(f"TRIGGER_SOURCE_RETRIEVAL_ALL: Found source '{source.name}' with {variables.count()} variables")
    
    if not variables.exists():
        logger.warning(f"TRIGGER_SOURCE_RETRIEVAL_ALL: No variables found for source '{source.name}'")
        messages.error(request, f"No variables found for source '{source.name}'. Please add variables first.")
        return redirect('data_pipeline:source_detail', source_id=source.id)
    
    if not source.is_active:
        logger.warning(f"TRIGGER_SOURCE_RETRIEVAL_ALL: Source '{source.name}' is inactive")
        messages.error(request, f"Source '{source.name}' is inactive. Please activate it before retrieving data.")
        return redirect('data_pipeline:source_detail', source_id=source.id)
    
    # Check for required environment variables based on source
    if source.class_name in ["IDMCGIDD", "IDMCIDU", "IDMC"] and not os.getenv('IDMC_API_KEY'):
        messages.error(request, "IDMC_API_KEY environment variable not set. Please configure it before running data retrieval.")
        return redirect('data_pipeline:source_detail', source_id=source.id)
    
    if source.class_name == "ACLED":
        if not os.getenv('ACLED_USERNAME'):
            messages.error(request, "ACLED_USERNAME environment variable not set. Please configure it before running data retrieval.")
            return redirect('data_pipeline:source_detail', source_id=source.id)
        if not os.getenv('ACLED_API_KEY'):
            messages.error(request, "ACLED_API_KEY environment variable not set. Please configure it before running data retrieval.")
            return redirect('data_pipeline:source_detail', source_id=source.id)
    
    if source.class_name == "IOM":
        if not os.getenv('IOM_API_KEY'):
            messages.error(request, "IOM_API_KEY environment variable not set. Please configure it before running data retrieval.")
            return redirect('data_pipeline:source_detail', source_id=source.id)
        if not os.getenv('IOM_APP'):
            messages.error(request, "IOM_APP environment variable not set. Please configure it before running data retrieval.")
            return redirect('data_pipeline:source_detail', source_id=source.id)
    
    try:
        # Check if async processing is requested
        use_async = request.POST.get('async', 'true') == 'true'
        variable_count = variables.count()
        
        if use_async:
            # Queue the pipeline task asynchronously
            logger.info(f"TRIGGER_SOURCE_RETRIEVAL_ALL: Queueing full_source_pipeline task for source '{source.name}' (ID: {source.id})")
            result = full_source_pipeline.delay(source.id)
            logger.info(f"TRIGGER_SOURCE_RETRIEVAL_ALL: Task queued with ID: {result.id}")
            messages.success(
                request,
                f"🚀 DATA RETRIEVAL: Data pipeline for all {variable_count} variable{'s' if variable_count != 1 else ''} "
                f"from '{source.name}' has been queued with single API call. "
                f"Task ID: {result.id}"
            )
        else:
            # Run synchronously
            result = full_source_pipeline.apply(args=[source.id])
            if result.result and result.result.get("success"):
                retrieved_count = result.result.get("retrieved_variables", 0)
                processed_count = result.result.get("processed_variables", 0) 
                messages.success(
                    request,
                    f"🎯 SUCCESS: Retrieved and processed {processed_count} of {variable_count} variable{'s' if variable_count != 1 else ''} "
                    f"from '{source.name}' using single API call."
                )
            else:
                error_msg = result.result.get("error", "Unknown error") if result.result else "Task failed"
                messages.error(
                    request,
                    f"Data retrieval failed for source '{source.name}': {error_msg}"
                )
        
        return redirect('data_pipeline:source_detail', source_id=source.id)
        
    except Exception as e:
        logger.error(f"TRIGGER_SOURCE_RETRIEVAL_ALL: Exception occurred for source '{source.name}': {str(e)}", exc_info=True)
        messages.error(
            request,
            f"Error triggering data retrieval for source '{source.name}': {str(e)}"
        )
        return redirect('data_pipeline:source_detail', source_id=source.id)


@login_required
def map_view(request):
    """Interactive map view for visualizing variable data geographically."""
    # Get filter options for the UI
    sources = Source.objects.filter(is_active=True).order_by('name')
    variables = Variable.objects.select_related('source').order_by('source__name', 'name')

    # Get date range from existing data
    date_range = VariableData.objects.aggregate(
        earliest=Min('start_date'),
        latest=Max('end_date')
    )

    # Default date filters (last 30 days)
    default_end_date = timezone.now().date()
    default_start_date = default_end_date - timedelta(days=30)

    # Convert variables to JSON-serializable format
    variables_data = [
        {
            'id': var.id,
            'name': var.name,
            'source': {
                'id': var.source.id,
                'name': var.source.name
            }
        }
        for var in variables
    ]

    context = {
        'sources': sources,
        'variables': variables,
        'variables_data': variables_data,
        'date_range': date_range,
        'default_start_date': default_start_date,
        'default_end_date': default_end_date,
    }

    return render(request, 'data_pipeline/map.html', context)


@login_required
@require_http_methods(["GET"])
def export_source_data(request, source_id):
    """Export all variable data for a source to Excel format."""
    import pandas as pd
    from django.http import HttpResponse

    source = get_object_or_404(Source, id=source_id)

    try:
        # Get all variable data for this source
        data_records = VariableData.objects.filter(
            variable__source=source
        ).select_related(
            'variable',
            'gid',
            'adm_level',
            'unmatched_location',
            'parent'
        ).order_by('variable__code', '-end_date')

        if not data_records.exists():
            messages.warning(request, f"No data available to export for source '{source.name}'.")
            return redirect('data_pipeline:source_detail', source_id=source.id)

        # Build data list following VariableData schema
        export_data = []
        for record in data_records:
            # Convert timezone-aware datetimes to timezone-naive for Excel compatibility
            created_at = record.created_at.replace(tzinfo=None) if record.created_at else None
            updated_at = record.updated_at.replace(tzinfo=None) if record.updated_at else None

            export_data.append({
                'id': record.id,
                'variable_id': record.variable.id,
                'variable_code': record.variable.code,
                'variable_name': record.variable.name,
                'start_date': record.start_date,
                'end_date': record.end_date,
                'period': record.period,
                'adm_level_id': record.adm_level.id,
                'adm_level_code': record.adm_level.code if hasattr(record.adm_level, 'code') else '',
                'adm_level_name': record.adm_level.name if hasattr(record.adm_level, 'name') else '',
                'gid': record.gid.id if record.gid else None,
                'geo_id': record.gid.geo_id if record.gid else '',
                'location_name': record.gid.name if record.gid else '',
                'latitude': float(record.gid.latitude) if record.gid and record.gid.latitude else None,
                'longitude': float(record.gid.longitude) if record.gid and record.gid.longitude else None,
                'original_location_text': record.original_location_text,
                'unmatched_location_id': record.unmatched_location.id if record.unmatched_location else None,
                'value': record.value,
                'text': record.text,
                'parent_id': record.parent.id if record.parent else None,
                'created_at': created_at,
                'updated_at': updated_at,
            })

        # Create DataFrame
        df = pd.DataFrame(export_data)

        # Create HTTP response with Excel file
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

        # Generate filename with timestamp
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{source.name.replace(' ', '_')}_{timestamp}.xlsx"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        # Write to Excel with openpyxl engine (pandas uses it by default)
        with pd.ExcelWriter(response, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Data', index=False)

            # Add a metadata sheet
            metadata = pd.DataFrame([
                {'Property': 'Source Name', 'Value': source.name},
                {'Property': 'Source Type', 'Value': source.get_type_display()},
                {'Property': 'Source Class', 'Value': source.class_name},
                {'Property': 'Export Date', 'Value': timezone.now().strftime('%Y-%m-%d %H:%M:%S')},
                {'Property': 'Total Records', 'Value': len(export_data)},
                {'Property': 'Variables Count', 'Value': source.variables.count()},
            ])
            metadata.to_excel(writer, sheet_name='Metadata', index=False)

        logger.info(f"Exported {len(export_data)} records for source '{source.name}' to Excel")
        return response

    except Exception as e:
        logger.error(f"Error exporting data for source '{source.name}': {str(e)}", exc_info=True)
        messages.error(
            request,
            f"Error exporting data for source '{source.name}': {str(e)}"
        )
        return redirect('data_pipeline:source_detail', source_id=source.id)
