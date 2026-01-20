"""Views for internal notification system."""

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db import models
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.generic import ListView

from .models import InternalNotification, NotificationPreference


class NotificationListView(LoginRequiredMixin, ListView):
    """List view for user notifications with filtering and pagination."""

    model = InternalNotification
    template_name = 'notifications/notification_list.html'
    context_object_name = 'notifications'
    paginate_by = 20

    def get_queryset(self):
        """Get notifications for current user with filtering."""
        queryset = InternalNotification.objects.filter(
            user=self.request.user
        ).select_related('alert').order_by('-created_at')

        # Filter by read status
        read_status = self.request.GET.get('read')
        if read_status == 'unread':
            queryset = queryset.filter(read=False)
        elif read_status == 'read':
            queryset = queryset.filter(read=True)

        # Filter by notification type
        notification_type = self.request.GET.get('type')
        if notification_type:
            queryset = queryset.filter(type=notification_type)

        # Filter by priority
        priority = self.request.GET.get('priority')
        if priority:
            queryset = queryset.filter(priority=priority)

        # Filter by date range
        date_from = self.request.GET.get('date_from')
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)

        date_to = self.request.GET.get('date_to')
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)

        return queryset

    def get_context_data(self, **kwargs):
        """Add filter context and statistics."""
        context = super().get_context_data(**kwargs)

        # Current filters
        context['current_filters'] = {
            'read': self.request.GET.get('read', ''),
            'type': self.request.GET.get('type', ''),
            'priority': self.request.GET.get('priority', ''),
            'date_from': self.request.GET.get('date_from', ''),
            'date_to': self.request.GET.get('date_to', ''),
        }

        # Statistics
        user_notifications = InternalNotification.objects.filter(user=self.request.user)
        context['stats'] = {
            'total': user_notifications.count(),
            'unread': user_notifications.filter(read=False).count(),
            'today': user_notifications.filter(
                created_at__date=timezone.now().date()
            ).count(),
            'this_week': user_notifications.filter(
                created_at__gte=timezone.now() - timezone.timedelta(days=7)
            ).count(),
        }

        # Choices for filters
        context['notification_types'] = InternalNotification.NOTIFICATION_TYPES
        context['priority_levels'] = InternalNotification.PRIORITY_LEVELS

        return context


@login_required
def notification_center(request):
    """Notification center dashboard."""
    user_notifications = InternalNotification.objects.filter(user=request.user)

    # Recent unread notifications
    recent_unread = user_notifications.filter(
        read=False
    ).select_related('alert').order_by('-created_at')[:10]

    # Statistics
    stats = {
        'total': user_notifications.count(),
        'unread': user_notifications.filter(read=False).count(),
        'today': user_notifications.filter(
            created_at__date=timezone.now().date()
        ).count(),
        'urgent': user_notifications.filter(
            priority='urgent',
            read=False
        ).count(),
    }

    # Type breakdown
    type_stats = {}
    for type_code, type_name in InternalNotification.NOTIFICATION_TYPES:
        count = user_notifications.filter(type=type_code).count()
        unread_count = user_notifications.filter(
            type=type_code,
            read=False
        ).count()
        # Calculate percentage for progress bar
        percentage = (count * 100 / stats['total']) if stats['total'] > 0 else 0

        type_stats[type_code] = {
            'name': type_name,
            'total': count,
            'unread': unread_count,
            'percentage': round(percentage, 1)
        }

    context = {
        'recent_unread': recent_unread,
        'stats': stats,
        'type_stats': type_stats,
    }

    return render(request, 'notifications/notification_center.html', context)


@login_required
@require_http_methods(["POST"])
def mark_notification_read(request, notification_id):
    """Mark a notification as read via AJAX."""
    try:
        notification = get_object_or_404(
            InternalNotification,
            id=notification_id,
            user=request.user
        )

        notification.mark_as_read()

        return JsonResponse({
            'success': True,
            'message': 'Notification marked as read'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
@require_http_methods(["POST"])
def mark_notification_unread(request, notification_id):
    """Mark a notification as unread via AJAX."""
    try:
        notification = get_object_or_404(
            InternalNotification,
            id=notification_id,
            user=request.user
        )

        notification.read = False
        notification.read_at = None
        notification.save(update_fields=['read', 'read_at'])

        return JsonResponse({
            'success': True,
            'message': 'Notification marked as unread'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
@require_http_methods(["POST"])
def mark_all_read(request):
    """Mark all notifications as read for the current user."""
    try:
        unread_notifications = InternalNotification.objects.filter(
            user=request.user,
            read=False
        )

        count = unread_notifications.count()
        unread_notifications.update(
            read=True,
            read_at=timezone.now()
        )

        return JsonResponse({
            'success': True,
            'message': f'Marked {count} notifications as read',
            'count': count
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
def api_notification_count(request):
    """Get unread notification count for AJAX."""
    try:
        unread_count = InternalNotification.objects.filter(
            user=request.user,
            read=False
        ).count()

        return JsonResponse({
            'success': True,
            'unread_count': unread_count
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
def api_recent_notifications(request):
    """Get recent notifications for dropdown."""
    try:
        limit = int(request.GET.get('limit', 5))
        notifications = InternalNotification.objects.filter(
            user=request.user
        ).select_related('alert').order_by('-created_at')[:limit]

        notification_data = []
        for notification in notifications:
            notification_data.append({
                'id': notification.id,
                'title': notification.title,
                'message': notification.message,
                'type': notification.type,
                'priority': notification.priority,
                'read': notification.read,
                'created_at': notification.created_at.isoformat(),
                'action_url': notification.action_url,
                'action_text': notification.action_text,
                'alert_id': notification.alert.id if notification.alert else None,
            })

        return JsonResponse({
            'success': True,
            'notifications': notification_data,
            'unread_count': InternalNotification.objects.filter(
                user=request.user,
                read=False
            ).count()
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)