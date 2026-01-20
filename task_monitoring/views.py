"""Views and API endpoints for task monitoring."""

from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Avg, Count, ExpressionWrapper, F, FloatField, Max, Q
from django.db.models.functions import Extract
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages

from .models import TaskExecution, TaskType


def get_duration_annotation():
    """Get duration annotation that works with both PostGIS and SpatiaLite."""
    # For SpatiaLite (testing), we need to use different approach
    if settings.TESTING or "spatialite" in settings.DATABASES["default"]["ENGINE"]:
        # SpatiaLite doesn't support Extract with DurationField, so we skip duration aggregation in tests
        return None
    else:
        # PostGIS supports Extract with DurationField
        return Avg(
            ExpressionWrapper(Extract(F("executions__completed_at") - F("executions__started_at"), "epoch"), output_field=FloatField()),
            filter=Q(executions__started_at__isnull=False, executions__completed_at__isnull=False),
        )


@login_required
def task_dashboard(request):
    """Dashboard view for task monitoring."""
    try:
        # Get summary statistics
        total_tasks = TaskExecution.objects.count()
        recent_tasks = TaskExecution.objects.filter(created_at__gte=timezone.now() - timedelta(days=7))

        annotations = {"total_executions": Count("executions"), "successful_executions": Count("executions", filter=Q(executions__status="success"))}

        # Add duration annotation only if supported
        duration_annotation = get_duration_annotation()
        if duration_annotation:
            annotations["avg_duration"] = duration_annotation

        task_types = TaskType.objects.annotate(**annotations).order_by("-total_executions")

        context = {
            "total_tasks": total_tasks,
            "recent_task_count": recent_tasks.count(),
            "task_types": task_types,
        }

    except Exception as e:
        # Handle database connection errors gracefully
        context = {
            "total_tasks": 0,
            "recent_task_count": 0,
            "task_types": [],
            "db_error": str(e),
        }

    return render(request, "task_monitoring/dashboard.html", context)


@login_required
@require_http_methods(["GET"])
def task_executions_api(request):
    """API endpoint to list task executions with filtering and pagination."""
    try:
        # Get query parameters
        task_type_id = request.GET.get("task_type")
        status = request.GET.get("status")
        source_id = request.GET.get("source")
        variable_id = request.GET.get("variable")
        start_date = request.GET.get("start_date")
        end_date = request.GET.get("end_date")
        page = int(request.GET.get("page", 1))
        page_size = min(int(request.GET.get("page_size", 50)), 1000)

        # Build query
        query = Q()

        if task_type_id:
            query &= Q(task_type_id=task_type_id)

        if status:
            query &= Q(status=status)

        if source_id:
            query &= Q(source_id=source_id)

        if variable_id:
            query &= Q(variable_id=variable_id)

        if start_date:
            query &= Q(created_at__gte=datetime.fromisoformat(start_date.replace("Z", "+00:00")))

        if end_date:
            query &= Q(created_at__lte=datetime.fromisoformat(end_date.replace("Z", "+00:00")))

        # Get executions
        executions = TaskExecution.objects.filter(query).select_related("task_type", "source", "variable").order_by("-created_at")

        # Paginate
        paginator = Paginator(executions, page_size)
        page_obj = paginator.get_page(page)

        # Serialize data
        data = []
        for execution in page_obj:
            data.append(
                {
                    "id": execution.id,
                    "task_id": execution.task_id,
                    "task_type": {"id": execution.task_type.id, "name": execution.task_type.name},
                    "status": execution.status,
                    "started_at": execution.started_at.isoformat() if execution.started_at else None,
                    "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
                    "duration_seconds": execution.duration_seconds,
                    "retry_count": execution.retry_count,
                    "max_retries": execution.max_retries,
                    "can_retry": execution.can_retry,
                    "source": {"id": execution.source.id, "name": execution.source.name} if execution.source else None,
                    "variable": {"id": execution.variable.id, "code": execution.variable.code, "name": execution.variable.name} if execution.variable else None,
                    "result": execution.result,
                    "error_message": execution.error_message,
                    "created_at": execution.created_at.isoformat(),
                    "updated_at": execution.updated_at.isoformat(),
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


@login_required
@require_http_methods(["GET"])
def task_types_api(request):
    """API endpoint to list task types with statistics."""
    try:
        annotations = {
            "total_executions": Count("executions"),
            "successful_executions": Count("executions", filter=Q(executions__status="success")),
            "failed_executions": Count("executions", filter=Q(executions__status="failure")),
        }

        # Add duration annotations only if supported
        if not (settings.TESTING or "spatialite" in settings.DATABASES["default"]["ENGINE"]):
            duration_expression = ExpressionWrapper(Extract(F("executions__completed_at") - F("executions__started_at"), "epoch"), output_field=FloatField())
            duration_filter = Q(executions__started_at__isnull=False, executions__completed_at__isnull=False)

            annotations["avg_duration"] = Avg(duration_expression, filter=duration_filter)
            annotations["max_duration"] = Max(duration_expression, filter=duration_filter)

        task_types = TaskType.objects.annotate(**annotations).order_by("name")

        data = []
        for task_type in task_types:
            success_rate = None
            if task_type.total_executions > 0:
                success_rate = (task_type.successful_executions / task_type.total_executions) * 100

            data.append(
                {
                    "id": task_type.id,
                    "name": task_type.name,
                    "statistics": {
                        "total_executions": task_type.total_executions,
                        "successful_executions": task_type.successful_executions,
                        "failed_executions": task_type.failed_executions,
                        "success_rate": round(success_rate, 2) if success_rate else None,
                        "avg_duration_seconds": round(task_type.avg_duration, 2) if hasattr(task_type, "avg_duration") and task_type.avg_duration else None,
                        "max_duration_seconds": getattr(task_type, "max_duration", None),
                    },
                    "created_at": task_type.created_at.isoformat(),
                    "updated_at": task_type.updated_at.isoformat(),
                }
            )

        return JsonResponse({"success": True, "data": data})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def task_statistics_api(request):
    """API endpoint for task execution statistics."""
    try:
        # Get date range from query parameters
        days = int(request.GET.get("days", 7))
        end_date = timezone.now()
        start_date = end_date - timedelta(days=days)

        executions = TaskExecution.objects.filter(created_at__gte=start_date, created_at__lte=end_date).select_related("task_type")

        # Overall statistics
        total_executions = executions.count()
        successful_executions = executions.filter(status="success").count()
        failed_executions = executions.filter(status="failure").count()

        success_rate = (successful_executions / total_executions * 100) if total_executions > 0 else 0

        # Statistics by task type
        type_stats = {}
        for execution in executions:
            task_type = execution.task_type.name
            if task_type not in type_stats:
                type_stats[task_type] = {"total": 0, "successful": 0, "failed": 0, "durations": []}

            type_stats[task_type]["total"] += 1

            if execution.status == "success":
                type_stats[task_type]["successful"] += 1
            elif execution.status == "failure":
                type_stats[task_type]["failed"] += 1

            if execution.duration_seconds:
                type_stats[task_type]["durations"].append(execution.duration_seconds)

        # Calculate averages for each type
        for _task_type, stats in type_stats.items():
            durations = stats["durations"]
            stats["avg_duration"] = sum(durations) / len(durations) if durations else None
            stats["max_duration"] = max(durations) if durations else None
            stats["success_rate"] = (stats["successful"] / stats["total"] * 100) if stats["total"] > 0 else 0
            del stats["durations"]  # Remove raw data

        # Daily breakdown
        daily_stats = {}
        for execution in executions:
            date_key = execution.created_at.date().isoformat()
            if date_key not in daily_stats:
                daily_stats[date_key] = {"total": 0, "successful": 0, "failed": 0}

            daily_stats[date_key]["total"] += 1
            if execution.status == "success":
                daily_stats[date_key]["successful"] += 1
            elif execution.status == "failure":
                daily_stats[date_key]["failed"] += 1

        return JsonResponse(
            {
                "success": True,
                "period": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat(), "days": days},
                "overall": {
                    "total_executions": total_executions,
                    "successful_executions": successful_executions,
                    "failed_executions": failed_executions,
                    "success_rate": round(success_rate, 2),
                },
                "by_type": type_stats,
                "by_day": daily_stats,
            }
        )

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def task_execution_detail_api(request, execution_id):
    """API endpoint to get detailed information about a task execution."""
    try:
        execution = TaskExecution.objects.select_related("task_type", "source", "variable").get(id=execution_id)

        data = {
            "id": execution.id,
            "task_id": execution.task_id,
            "task_type": {"id": execution.task_type.id, "name": execution.task_type.name},
            "status": execution.status,
            "started_at": execution.started_at.isoformat() if execution.started_at else None,
            "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
            "duration_seconds": execution.duration_seconds,
            "retry_count": execution.retry_count,
            "max_retries": execution.max_retries,
            "can_retry": execution.can_retry,
            "is_completed": execution.is_completed,
            "source": {"id": execution.source.id, "name": execution.source.name, "type": execution.source.type} if execution.source else None,
            "variable": {"id": execution.variable.id, "code": execution.variable.code, "name": execution.variable.name, "type": execution.variable.type}
            if execution.variable
            else None,
            "result": execution.result,
            "error_message": execution.error_message,
            "arg1": execution.arg1,
            "created_at": execution.created_at.isoformat(),
            "updated_at": execution.updated_at.isoformat(),
        }

        return JsonResponse({"success": True, "data": data})

    except TaskExecution.DoesNotExist:
        return JsonResponse({"success": False, "error": f"Task execution with id {execution_id} not found"}, status=404)

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
def queue_monitoring(request):
    """View to monitor Celery queues and Redis state."""
    context = {
        'queues': [],
        'redis_info': {},
        'error': None
    }
    
    try:
        # Import Celery app and Redis
        from app.celery import app as celery_app
        import redis
        from django.conf import settings
        
        # Connect to Redis
        redis_client = redis.Redis.from_url(settings.CELERY_BROKER_URL)
        
        # Get Redis info
        context['redis_info'] = {
            'connected': True,
            'memory_usage': redis_client.info().get('used_memory_human', 'N/A'),
            'total_keys': redis_client.dbsize(),
            'version': redis_client.info().get('redis_version', 'Unknown')
        }
        
        # Get queue information
        inspect = celery_app.control.inspect()
        active_tasks = inspect.active() or {}
        scheduled_tasks = inspect.scheduled() or {}
        reserved_tasks = inspect.reserved() or {}
        
        # Get queue lengths from Redis
        queue_names = ['default', 'data_retrieval', 'data_processing', 'data_aggregation', 'pipeline']
        
        queues = []
        for queue_name in queue_names:
            queue_key = f"celery"
            if queue_name != 'default':
                queue_key = f"celery@{queue_name}"
                
            # Get queue length from Redis
            queue_length = redis_client.llen(queue_name)
            
            # Count tasks by queue for each worker
            queue_active = 0
            queue_scheduled = 0
            queue_reserved = 0
            
            for worker, tasks in active_tasks.items():
                queue_active += len([t for t in tasks if t.get('delivery_info', {}).get('routing_key', 'default') == queue_name])
                
            for worker, tasks in scheduled_tasks.items():
                queue_scheduled += len([t for t in tasks if t.get('delivery_info', {}).get('routing_key', 'default') == queue_name])
                
            for worker, tasks in reserved_tasks.items():
                queue_reserved += len([t for t in tasks if t.get('delivery_info', {}).get('routing_key', 'default') == queue_name])
            
            queues.append({
                'name': queue_name,
                'length': queue_length,
                'active_tasks': queue_active,
                'scheduled_tasks': queue_scheduled,
                'reserved_tasks': queue_reserved,
                'total_tasks': queue_length + queue_active + queue_scheduled + queue_reserved
            })
        
        context['queues'] = queues
        
        # Get detailed task information
        all_tasks = []
        for worker, tasks in active_tasks.items():
            for task in tasks:
                all_tasks.append({
                    'id': task.get('id'),
                    'name': task.get('name'),
                    'args': task.get('args', []),
                    'kwargs': task.get('kwargs', {}),
                    'worker': worker,
                    'status': 'active',
                    'queue': task.get('delivery_info', {}).get('routing_key', 'default'),
                    'eta': task.get('eta'),
                    'retries': task.get('retries', 0)
                })
        
        for worker, tasks in scheduled_tasks.items():
            for task in tasks:
                all_tasks.append({
                    'id': task.get('id'),
                    'name': task.get('name'),
                    'args': task.get('args', []),
                    'kwargs': task.get('kwargs', {}),
                    'worker': worker,
                    'status': 'scheduled',
                    'queue': task.get('delivery_info', {}).get('routing_key', 'default'),
                    'eta': task.get('eta'),
                    'retries': task.get('retries', 0)
                })
        
        for worker, tasks in reserved_tasks.items():
            for task in tasks:
                all_tasks.append({
                    'id': task.get('id'),
                    'name': task.get('name'), 
                    'args': task.get('args', []),
                    'kwargs': task.get('kwargs', {}),
                    'worker': worker,
                    'status': 'reserved',
                    'queue': task.get('delivery_info', {}).get('routing_key', 'default'),
                    'eta': task.get('eta'),
                    'retries': task.get('retries', 0)
                })
        
        context['all_tasks'] = all_tasks
        
        # Get worker information
        stats = inspect.stats() or {}
        workers = []
        for worker_name, worker_stats in stats.items():
            workers.append({
                'name': worker_name,
                'status': 'online',
                'load': worker_stats.get('total', {}),
                'processes': worker_stats.get('pool', {}).get('processes', 0),
                'max_concurrency': worker_stats.get('pool', {}).get('max-concurrency', 0)
            })
        
        context['workers'] = workers
        
    except ImportError as e:
        context['error'] = f"Celery or Redis not available: {str(e)}"
    except Exception as e:
        context['error'] = f"Error connecting to queue system: {str(e)}"
    
    return render(request, 'task_monitoring/queue_monitoring.html', context)


@login_required
@require_http_methods(["POST"])
def clear_queue(request, queue_name):
    """Clear all tasks from a specific queue."""
    try:
        import redis
        from django.conf import settings
        
        # Connect to Redis
        redis_client = redis.Redis.from_url(settings.CELERY_BROKER_URL)
        
        # Clear the queue
        cleared_count = redis_client.delete(queue_name)
        
        messages.success(request, f"Cleared queue '{queue_name}' - removed {cleared_count} tasks")
        
    except Exception as e:
        messages.error(request, f"Error clearing queue '{queue_name}': {str(e)}")
    
    return JsonResponse({"success": True, "redirect": request.META.get('HTTP_REFERER', '/tasks/queues/')})


@login_required
@require_http_methods(["POST"])
def revoke_task(request, task_id):
    """Revoke a specific task."""
    try:
        from app.celery import app as celery_app
        
        # Revoke the task
        celery_app.control.revoke(task_id, terminate=True)
        
        messages.success(request, f"Revoked task {task_id}")
        
    except Exception as e:
        messages.error(request, f"Error revoking task {task_id}: {str(e)}")
    
    return JsonResponse({"success": True, "redirect": request.META.get('HTTP_REFERER', '/tasks/queues/')})
