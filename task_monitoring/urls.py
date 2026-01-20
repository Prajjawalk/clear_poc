"""URL patterns for task monitoring views and API."""

from django.urls import path

from . import log_views
from . import views
from .scheduled_views import (
    TaskExecutionListView,
    create_scheduled_task,
    delete_scheduled_task,
    run_scheduled_task,
    scheduled_task_detail,
    scheduled_tasks_list,
    toggle_scheduled_task,
)

app_name = "task_monitoring"

urlpatterns = [
    # Dashboard and main views
    path("", views.task_dashboard, name="dashboard"),
    path("executions/", TaskExecutionListView.as_view(), name="task_executions_list"),
    path("queues/", views.queue_monitoring, name="queue_monitoring"),
    # Scheduled tasks management
    path("scheduled/", scheduled_tasks_list, name="scheduled_tasks_list"),
    path("scheduled/create/", create_scheduled_task, name="create_scheduled_task"),
    path("scheduled/<int:task_id>/", scheduled_task_detail, name="scheduled_task_detail"),
    path("scheduled/<int:task_id>/toggle/", toggle_scheduled_task, name="toggle_scheduled_task"),
    path("scheduled/<int:task_id>/delete/", delete_scheduled_task, name="delete_scheduled_task"),
    path("scheduled/<int:task_id>/run/", run_scheduled_task, name="run_scheduled_task"),
    # Queue management
    path("queues/<str:queue_name>/clear/", views.clear_queue, name="clear_queue"),
    path("tasks/<str:task_id>/revoke/", views.revoke_task, name="revoke_task"),
    # Task logs
    path("logs/", log_views.task_logs_list, name="logs_list"),
    path("logs/clear-all/", log_views.task_logs_clear_all, name="logs_clear_all"),
    path("logs/<str:task_id>/", log_views.task_logs_detail, name="logs_detail"),
    path("logs/api/<str:task_id>/", log_views.task_logs_api, name="logs_api"),
    path("logs/export/<str:task_id>/", log_views.task_logs_export, name="logs_export"),
    path("logs/clear/<str:task_id>/", log_views.task_logs_clear, name="logs_clear"),
    # API endpoints
    path("api/executions/", views.task_executions_api, name="executions_api"),
    path("api/executions/<int:execution_id>/", views.task_execution_detail_api, name="execution_detail_api"),
    path("api/types/", views.task_types_api, name="types_api"),
    path("api/statistics/", views.task_statistics_api, name="statistics_api"),
]
