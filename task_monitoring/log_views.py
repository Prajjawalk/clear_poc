"""Views for task log display and monitoring."""

import json
from datetime import timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect

from .models import TaskExecution, TaskLog


@staff_member_required
def task_logs_list(request):
    """Display a list of task logs with filtering capabilities."""
    # Get filter parameters
    task_id = request.GET.get('task_id', '')
    level = request.GET.get('level', '')
    search = request.GET.get('search', '')
    hours = request.GET.get('hours', '24')

    # Build queryset
    logs = TaskLog.objects.select_related().order_by('-timestamp')

    # Apply filters
    if task_id:
        logs = logs.filter(task_id__icontains=task_id)

    if level:
        logs = logs.filter(level=int(level))

    if search:
        logs = logs.filter(
            Q(message__icontains=search) |
            Q(module__icontains=search) |
            Q(function_name__icontains=search)
        )

    # Time range filter
    try:
        hours_int = int(hours)
        if hours_int > 0:
            cutoff_time = timezone.now() - timedelta(hours=hours_int)
            logs = logs.filter(timestamp__gte=cutoff_time)
    except (ValueError, TypeError):
        pass

    # Pagination
    paginator = Paginator(logs, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Get unique task IDs for filter dropdown
    recent_task_ids = TaskLog.objects.filter(
        timestamp__gte=timezone.now() - timedelta(days=7)
    ).values_list('task_id', flat=True).distinct()[:20]

    context = {
        'page_obj': page_obj,
        'logs': page_obj.object_list,
        'recent_task_ids': recent_task_ids,
        'level_choices': TaskLog.LEVEL_CHOICES,
        'current_filters': {
            'task_id': task_id,
            'level': level,
            'search': search,
            'hours': hours,
        },
    }

    return render(request, 'task_monitoring/logs_list.html', context)


@staff_member_required
def task_logs_detail(request, task_id):
    """Display detailed logs for a specific task."""
    # Get the task execution if it exists
    task_execution = None
    try:
        task_execution = TaskExecution.objects.get(task_id=task_id)
    except TaskExecution.DoesNotExist:
        pass

    # Get logs for this task
    logs = TaskLog.objects.filter(task_id=task_id).order_by('timestamp')

    # Check if task is currently running
    is_running = False
    if task_execution:
        is_running = task_execution.status in ['pending', 'started']

    # Get pagination
    paginator = Paginator(logs, 100)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Calculate log statistics
    log_stats = {
        'total': logs.count(),
        'debug': logs.filter(level=10).count(),
        'info': logs.filter(level=20).count(),
        'warning': logs.filter(level=30).count(),
        'error': logs.filter(level=40).count(),
        'critical': logs.filter(level=50).count(),
    }

    context = {
        'task_id': task_id,
        'task_execution': task_execution,
        'page_obj': page_obj,
        'logs': page_obj.object_list,
        'log_stats': log_stats,
        'is_running': is_running,
        'level_choices': TaskLog.LEVEL_CHOICES,
    }

    return render(request, 'task_monitoring/logs_detail.html', context)


@staff_member_required
def task_logs_api(request, task_id):
    """API endpoint for real-time log updates."""
    # Get query parameters
    since_timestamp = request.GET.get('since')
    level_filter = request.GET.get('level')
    limit = min(int(request.GET.get('limit', 50)), 100)  # Max 100 logs

    # Build queryset
    logs = TaskLog.objects.filter(task_id=task_id).order_by('timestamp')

    # Apply filters
    if since_timestamp:
        try:
            from datetime import datetime
            # Parse ISO format timestamp
            since_dt = datetime.fromisoformat(since_timestamp.replace('Z', '+00:00'))
            logs = logs.filter(timestamp__gt=since_dt)
        except (ValueError, TypeError):
            pass

    if level_filter:
        try:
            logs = logs.filter(level=int(level_filter))
        except (ValueError, TypeError):
            pass

    # Limit results
    logs = logs[:limit]

    # Serialize logs
    log_data = []
    for log in logs:
        log_data.append({
            'id': log.id,
            'timestamp': log.timestamp.isoformat(),
            'level': log.level,
            'level_name': log.level_name,
            'level_color': log.level_color,
            'level_icon': log.level_icon,
            'message': log.message,
            'module': log.module,
            'function_name': log.function_name,
            'line_number': log.line_number,
            'thread': log.thread,
            'process': log.process,
            'extra_data': log.extra_data,
        })

    # Check if task is still running
    is_running = False
    try:
        execution = TaskExecution.objects.get(task_id=task_id)
        is_running = execution.status in ['pending', 'started']
    except TaskExecution.DoesNotExist:
        pass

    return JsonResponse({
        'success': True,
        'logs': log_data,
        'is_running': is_running,
        'count': len(log_data),
        'has_more': len(log_data) >= limit,
    })


@staff_member_required
def task_logs_stream(request, task_id):
    """Stream logs for a specific task (Server-Sent Events)."""
    # This would implement SSE for real-time streaming
    # For now, we'll use polling via the API endpoint
    return JsonResponse({
        'message': 'Use the logs API endpoint for real-time updates',
        'api_url': f'/tasks/logs/api/{task_id}/',
    })


@staff_member_required
def task_logs_export(request, task_id):
    """Export task logs as JSON or text format."""
    format_type = request.GET.get('format', 'json')

    # Get all logs for this task
    logs = TaskLog.objects.filter(task_id=task_id).order_by('timestamp')

    if format_type == 'text':
        # Export as plain text log format
        from django.http import HttpResponse

        response = HttpResponse(content_type='text/plain')
        response['Content-Disposition'] = f'attachment; filename="task-{task_id}-logs.txt"'

        for log in logs:
            timestamp = log.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            line = f"[{timestamp}] {log.level_name}: {log.message}\n"
            if log.module:
                line = f"[{timestamp}] {log.level_name} {log.module}:{log.line_number or ''}: {log.message}\n"
            response.write(line)

        return response

    else:
        # Export as JSON
        from django.http import HttpResponse

        log_data = []
        for log in logs:
            log_data.append({
                'timestamp': log.timestamp.isoformat(),
                'level': log.level,
                'level_name': log.level_name,
                'message': log.message,
                'module': log.module,
                'function_name': log.function_name,
                'line_number': log.line_number,
                'thread': log.thread,
                'process': log.process,
                'extra_data': log.extra_data,
            })

        response = HttpResponse(
            json.dumps(log_data, indent=2),
            content_type='application/json'
        )
        response['Content-Disposition'] = f'attachment; filename="task-{task_id}-logs.json"'

        return response


@staff_member_required
def task_logs_clear(request, task_id):
    """Clear logs for a specific task (POST only)."""
    if request.method == 'POST':
        deleted_count, _ = TaskLog.objects.filter(task_id=task_id).delete()

        return JsonResponse({
            'success': True,
            'message': f'Deleted {deleted_count} log entries for task {task_id}',
            'deleted_count': deleted_count,
        })

    return JsonResponse({
        'success': False,
        'error': 'Only POST method allowed',
    }, status=405)


@staff_member_required
@require_POST
@csrf_protect
def task_logs_clear_all(request):
    """Clear all task logs (POST only)."""
    try:
        deleted_count, _ = TaskLog.objects.all().delete()

        return JsonResponse({
            'success': True,
            'message': f'Deleted all {deleted_count} log entries',
            'deleted_count': deleted_count,
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Error deleting logs: {str(e)}',
        }, status=500)