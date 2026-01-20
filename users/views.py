"""User management views."""

from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.models import User
from django.db import models
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.generic import CreateView, ListView, UpdateView

from .forms import UserCreateForm, UserProfileForm
from .models import UserProfile


class UserProfileUpdateView(LoginRequiredMixin, UpdateView):
    """Allow users to update their own profile."""

    model = UserProfile
    form_class = UserProfileForm
    template_name = 'users/profile_form.html'
    success_url = reverse_lazy('users:profile')

    def get_object(self):
        """Get the current user's profile."""
        profile, created = UserProfile.objects.get_or_create(user=self.request.user)
        return profile

    def form_valid(self, form):
        """Add success message when profile is updated."""
        messages.success(self.request, 'Your profile has been updated successfully.')
        return super().form_valid(form)


@login_required
def profile_view(request):
    """Display user profile with notification settings."""
    profile, created = UserProfile.objects.get_or_create(user=request.user)

    # Get user's subscriptions
    from alerts.models import Subscription
    subscriptions = Subscription.objects.filter(user=request.user).prefetch_related(
        'locations', 'shock_types'
    )

    # Get notification statistics
    from notifications.models import InternalNotification
    notification_stats = {
        'total': InternalNotification.objects.filter(user=request.user).count(),
        'unread': InternalNotification.objects.filter(user=request.user, read=False).count(),
        'this_week': InternalNotification.objects.filter(
            user=request.user,
            created_at__gte=timezone.now() - timezone.timedelta(days=7)
        ).count(),
    }

    context = {
        'profile': profile,
        'subscriptions': subscriptions,
        'notification_stats': notification_stats,
    }

    return render(request, 'users/profile.html', context)


@login_required
@require_http_methods(["POST"])
def request_email_verification(request):
    """Send email verification to user."""
    profile = request.user.profile

    if profile.email_verified:
        messages.info(request, 'Your email is already verified.')
        return redirect('users:profile')

    # Check if verification was sent recently (within 5 minutes)
    if (profile.email_verification_sent_at and
        timezone.now() - profile.email_verification_sent_at < timezone.timedelta(minutes=5)):
        messages.warning(
            request,
            'Verification email was sent recently. Please wait 5 minutes before requesting another.'
        )
        return redirect('users:profile')

    # Queue verification email
    from alerts.tasks import send_email_verification
    import logging
    logger = logging.getLogger(__name__)

    logger.info(f"QUEUING email verification task for user {request.user.id} ({request.user.email})")
    task = send_email_verification.delay(request.user.id)
    logger.info(f"Task queued with ID: {task.id}")

    messages.success(
        request,
        f'Verification email has been sent to {request.user.email}. Please check your inbox.'
    )

    return redirect('users:profile')


def verify_email(request, token):
    """Verify user email with token."""
    try:
        profile = UserProfile.objects.get(email_verification_token=token)

        if profile.email_verified:
            messages.info(request, 'Your email is already verified.')
        else:
            profile.email_verified = True
            profile.email_verification_token = ''  # Clear token
            profile.save(update_fields=['email_verified', 'email_verification_token'])

            messages.success(request, 'Your email has been verified successfully! You can now receive email notifications.')

            # Auto-login if user is not authenticated
            if not request.user.is_authenticated:
                login(request, profile.user)

        return redirect('users:profile')

    except UserProfile.DoesNotExist:
        messages.error(request, 'Invalid verification token. Please request a new verification email.')
        return redirect('users:profile')


@login_required
def change_password(request):
    """Change user password."""
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # Keep user logged in
            messages.success(request, 'Your password has been changed successfully.')
            return redirect('users:profile')
    else:
        form = PasswordChangeForm(request.user)

    return render(request, 'users/change_password.html', {'form': form})


# Admin views (staff only)

@user_passes_test(lambda u: u.is_staff)
def admin_dashboard(request):
    """Admin dashboard with user statistics."""
    user_stats = {
        'total_users': User.objects.count(),
        'verified_users': UserProfile.objects.filter(email_verified=True).count(),
        'notification_enabled': UserProfile.objects.filter(email_notifications_enabled=True).count(),
        'recent_signups': User.objects.filter(
            date_joined__gte=timezone.now() - timezone.timedelta(days=7)
        ).count(),
    }

    # Recent users
    recent_users = User.objects.select_related('profile').order_by('-date_joined')[:10]

    context = {
        'user_stats': user_stats,
        'recent_users': recent_users,
    }

    return render(request, 'users/admin/dashboard.html', context)


class AdminUserCreateView(UserPassesTestMixin, CreateView):
    """Admin interface for creating users."""

    model = User
    form_class = UserCreateForm
    template_name = 'users/admin/user_create.html'
    success_url = reverse_lazy('users:admin_user_list')

    def test_func(self):
        """Only allow staff users."""
        return self.request.user.is_staff

    def form_valid(self, form):
        """Create user and send verification email."""
        response = super().form_valid(form)

        # Send verification email if email provided
        if self.object.email:
            from alerts.tasks import send_email_verification
            send_email_verification.delay(self.object.id)

            messages.success(
                self.request,
                f'User {self.object.username} created successfully. Verification email sent.'
            )
        else:
            messages.success(
                self.request,
                f'User {self.object.username} created successfully.'
            )

        return response


class AdminUserListView(UserPassesTestMixin, ListView):
    """Admin interface for listing users."""

    model = User
    template_name = 'users/admin/user_list.html'
    context_object_name = 'users'
    paginate_by = 25

    def test_func(self):
        """Only allow staff users."""
        return self.request.user.is_staff

    def get_queryset(self):
        """Get users with profile information."""
        queryset = User.objects.select_related('profile').order_by('-date_joined')

        # Search functionality
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                models.Q(username__icontains=search) |
                models.Q(email__icontains=search) |
                models.Q(first_name__icontains=search) |
                models.Q(last_name__icontains=search)
            )

        # Filter by email verification status
        verified = self.request.GET.get('verified')
        if verified == 'true':
            queryset = queryset.filter(profile__email_verified=True)
        elif verified == 'false':
            queryset = queryset.filter(profile__email_verified=False)

        # Filter by notification enabled status
        notifications = self.request.GET.get('notifications')
        if notifications == 'true':
            queryset = queryset.filter(profile__email_notifications_enabled=True)
        elif notifications == 'false':
            queryset = queryset.filter(profile__email_notifications_enabled=False)

        return queryset

    def get_context_data(self, **kwargs):
        """Add filter context."""
        context = super().get_context_data(**kwargs)
        context['current_filters'] = {
            'search': self.request.GET.get('search', ''),
            'verified': self.request.GET.get('verified', ''),
            'notifications': self.request.GET.get('notifications', ''),
        }
        return context


@user_passes_test(lambda u: u.is_staff)
@require_http_methods(["POST"])
def admin_bulk_action(request):
    """Handle bulk actions on users."""
    action = request.POST.get('action')
    user_ids = request.POST.getlist('user_ids')

    if not user_ids:
        messages.error(request, 'No users selected.')
        return redirect('users:admin_user_list')

    users = User.objects.filter(id__in=user_ids)

    if action == 'enable_notifications':
        UserProfile.objects.filter(user__in=users).update(email_notifications_enabled=True)
        messages.success(request, f'Enabled email notifications for {len(user_ids)} users.')

    elif action == 'disable_notifications':
        UserProfile.objects.filter(user__in=users).update(email_notifications_enabled=False)
        messages.success(request, f'Disabled email notifications for {len(user_ids)} users.')

    elif action == 'verify_emails':
        UserProfile.objects.filter(user__in=users).update(email_verified=True)
        messages.success(request, f'Marked {len(user_ids)} emails as verified.')

    elif action == 'send_verification':
        from alerts.tasks import send_email_verification
        for user_id in user_ids:
            send_email_verification.delay(int(user_id))
        messages.success(request, f'Sent verification emails to {len(user_ids)} users.')

    else:
        messages.error(request, 'Invalid action.')

    return redirect('users:admin_user_list')


@login_required
def notification_preferences(request):
    """Manage notification preferences."""
    from notifications.models import NotificationPreference

    preferences, created = NotificationPreference.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        # Update preferences based on form data
        preferences.internal_enabled = request.POST.get('internal_enabled') == 'on'
        preferences.alert_notifications = request.POST.get('alert_notifications') == 'on'
        preferences.system_notifications = request.POST.get('system_notifications') == 'on'
        preferences.update_notifications = request.POST.get('update_notifications') == 'on'
        preferences.feedback_notifications = request.POST.get('feedback_notifications') == 'on'
        preferences.show_desktop_notifications = request.POST.get('show_desktop_notifications') == 'on'
        preferences.play_sound = request.POST.get('play_sound') == 'on'
        preferences.quiet_hours_enabled = request.POST.get('quiet_hours_enabled') == 'on'

        # Handle quiet hours
        if preferences.quiet_hours_enabled:
            start_time = request.POST.get('quiet_hours_start')
            end_time = request.POST.get('quiet_hours_end')
            if start_time:
                preferences.quiet_hours_start = start_time
            if end_time:
                preferences.quiet_hours_end = end_time

        preferences.save()

        messages.success(request, 'Notification preferences updated successfully.')
        return redirect('users:notification_preferences')

    return render(request, 'users/notification_preferences.html', {
        'preferences': preferences
    })


# API endpoints for AJAX

@login_required
def api_toggle_email_notifications(request):
    """Toggle email notifications via AJAX."""
    if request.method == 'POST':
        profile = request.user.profile
        profile.email_notifications_enabled = not profile.email_notifications_enabled
        profile.save(update_fields=['email_notifications_enabled'])

        return JsonResponse({
            'success': True,
            'enabled': profile.email_notifications_enabled,
            'message': 'Email notifications ' + ('enabled' if profile.email_notifications_enabled else 'disabled')
        })

    return JsonResponse({'success': False, 'error': 'Invalid request method'})