/**
 * Notification system JavaScript
 * Handles real-time notification updates and user interactions
 */

class NotificationManager {
    constructor() {
        this.unreadCount = 0;
        this.updateInterval = 30000; // 30 seconds
        this.notificationBell = document.getElementById('notificationBell');
        this.notificationBadge = document.getElementById('notificationBadge');
        this.unreadCountElement = document.getElementById('unreadCount');
        this.notificationList = document.getElementById('notificationList');
        this.markAllReadBtn = document.getElementById('markAllReadBtn');

        this.init();
    }

    init() {
        // Initial load
        this.loadNotificationCount();
        this.loadRecentNotifications();

        // Set up periodic updates
        setInterval(() => {
            this.loadNotificationCount();
        }, this.updateInterval);

        // Set up event listeners
        this.setupEventListeners();
    }

    setupEventListeners() {
        // Mark all read button
        if (this.markAllReadBtn) {
            this.markAllReadBtn.addEventListener('click', () => {
                this.markAllAsRead();
            });
        }

        // Refresh notifications when dropdown opens
        if (this.notificationBell) {
            this.notificationBell.addEventListener('click', () => {
                this.loadRecentNotifications();
            });
        }
    }

    async loadNotificationCount() {
        try {
            const response = await fetch('/notifications/api/count/');
            const data = await response.json();

            if (data.success) {
                this.updateUnreadCount(data.unread_count);
            }
        } catch (error) {
            console.error('Error loading notification count:', error);
        }
    }

    async loadRecentNotifications() {
        try {
            const response = await fetch('/notifications/api/recent/?limit=5');
            const data = await response.json();

            if (data.success) {
                this.renderNotifications(data.notifications);
                this.updateUnreadCount(data.unread_count);
            }
        } catch (error) {
            console.error('Error loading recent notifications:', error);
        }
    }

    updateUnreadCount(count) {
        this.unreadCount = count;

        if (this.unreadCountElement) {
            this.unreadCountElement.textContent = count;
        }

        if (this.notificationBadge) {
            if (count > 0) {
                this.notificationBadge.style.display = 'block';
            } else {
                this.notificationBadge.style.display = 'none';
            }
        }

        if (this.markAllReadBtn) {
            if (count > 0) {
                this.markAllReadBtn.style.display = 'inline-block';
            } else {
                this.markAllReadBtn.style.display = 'none';
            }
        }
    }

    renderNotifications(notifications) {
        if (!this.notificationList) return;

        if (notifications.length === 0) {
            this.notificationList.innerHTML = `
                <li class="dropdown-item-text text-center text-muted py-3">
                    <i class="bi bi-bell-slash"></i><br>
                    No notifications
                </li>
            `;
            return;
        }

        const notificationsHtml = notifications.map(notification => {
            const timeAgo = this.formatTimeAgo(new Date(notification.created_at));
            const priorityClass = this.getPriorityClass(notification.priority);
            const typeIcon = this.getTypeIcon(notification.type);

            return `
                <li class="dropdown-item notification-item ${notification.read ? '' : 'unread'} ${notification.action_url ? 'clickable' : ''}"
                    data-notification-id="${notification.id}"
                    ${notification.action_url ? `data-action-url="${notification.action_url}"` : ''}>
                    <div class="d-flex align-items-start">
                        <div class="me-2">
                            <i class="bi ${typeIcon} ${priorityClass}"></i>
                        </div>
                        <div class="flex-grow-1">
                            <div class="fw-bold small mb-1 notification-title">${this.escapeHtml(notification.title)}</div>
                            <div class="text-muted small mb-1 notification-message">${this.escapeHtml(notification.message)}</div>
                            <div class="d-flex justify-content-between align-items-center">
                                <small class="text-muted">${timeAgo}</small>
                                ${!notification.read ? `
                                    <button class="btn btn-sm btn-outline-secondary mark-read-btn"
                                            data-notification-id="${notification.id}"
                                            style="font-size: 0.75rem; padding: 0.25rem 0.5rem;"
                                            title="Mark as read">
                                        <i class="bi bi-check"></i>
                                    </button>
                                ` : ''}
                            </div>
                        </div>
                    </div>
                </li>
            `;
        }).join('');

        this.notificationList.innerHTML = notificationsHtml;

        // Add event listeners for mark as read buttons
        this.notificationList.querySelectorAll('.mark-read-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                const notificationId = btn.dataset.notificationId;
                this.markAsRead(notificationId);
            });
        });

        // Add event listeners for clickable notifications
        this.notificationList.querySelectorAll('.notification-item.clickable').forEach(item => {
            item.addEventListener('click', (e) => {
                // Don't trigger if clicking on mark-read button
                if (e.target.closest('.mark-read-btn')) {
                    return;
                }

                const actionUrl = item.dataset.actionUrl;
                const notificationId = item.dataset.notificationId;

                if (actionUrl) {
                    // Mark as read if unread
                    if (item.classList.contains('unread')) {
                        this.markAsRead(notificationId, false); // Don't show toast
                    }

                    // Navigate to the URL
                    window.location.href = actionUrl;
                }
            });
        });
    }

    async markAsRead(notificationId, showToast = true) {
        try {
            const response = await fetch(`/notifications/api/mark-read/${notificationId}/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                }
            });

            const data = await response.json();

            if (data.success) {
                // Refresh notifications
                this.loadRecentNotifications();
                if (showToast) {
                    this.showToast('Notification marked as read', 'success');
                }
            } else {
                if (showToast) {
                    this.showToast('Error marking notification as read', 'error');
                }
            }
        } catch (error) {
            console.error('Error marking notification as read:', error);
            if (showToast) {
                this.showToast('Error marking notification as read', 'error');
            }
        }
    }

    async markAllAsRead() {
        try {
            const response = await fetch('/notifications/api/mark-all-read/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                }
            });

            const data = await response.json();

            if (data.success) {
                // Refresh notifications
                this.loadRecentNotifications();
                this.showToast(`Marked ${data.count} notifications as read`, 'success');
            } else {
                this.showToast('Error marking notifications as read', 'error');
            }
        } catch (error) {
            console.error('Error marking all notifications as read:', error);
            this.showToast('Error marking notifications as read', 'error');
        }
    }

    getCSRFToken() {
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
            const [name, value] = cookie.trim().split('=');
            if (name === 'csrftoken') {
                return value;
            }
        }
        return '';
    }

    formatTimeAgo(date) {
        const now = new Date();
        const diffMs = now - date;
        const diffMins = Math.floor(diffMs / (1000 * 60));
        const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
        const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

        if (diffMins < 1) {
            return 'Just now';
        } else if (diffMins < 60) {
            return `${diffMins}m ago`;
        } else if (diffHours < 24) {
            return `${diffHours}h ago`;
        } else if (diffDays < 7) {
            return `${diffDays}d ago`;
        } else {
            return date.toLocaleDateString();
        }
    }

    getPriorityClass(priority) {
        switch (priority) {
            case 'urgent':
                return 'text-danger';
            case 'high':
                return 'text-warning';
            case 'medium':
                return 'text-info';
            case 'low':
                return 'text-secondary';
            default:
                return 'text-muted';
        }
    }

    getTypeIcon(type) {
        switch (type) {
            case 'alert':
                return 'bi-exclamation-triangle';
            case 'data_update':
                return 'bi-arrow-clockwise';
            case 'system':
                return 'bi-gear';
            case 'user':
                return 'bi-person';
            default:
                return 'bi-bell';
        }
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    truncateText(text, maxLength) {
        if (text.length <= maxLength) {
            return text;
        }
        return text.substring(0, maxLength - 3) + '...';
    }

    showToast(message, type = 'info') {
        // Create toast container if it doesn't exist
        let toastContainer = document.getElementById('toastContainer');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.id = 'toastContainer';
            toastContainer.className = 'toast-container position-fixed top-0 end-0 p-3';
            toastContainer.style.zIndex = '9999';
            document.body.appendChild(toastContainer);
        }

        // Create toast
        const toastId = `toast-${Date.now()}`;
        const toast = document.createElement('div');
        toast.id = toastId;
        toast.className = `toast align-items-center text-bg-${type === 'error' ? 'danger' : 'success'} border-0`;
        toast.setAttribute('role', 'alert');
        toast.setAttribute('aria-live', 'assertive');
        toast.setAttribute('aria-atomic', 'true');

        toast.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">
                    ${this.escapeHtml(message)}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto"
                        data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        `;

        toastContainer.appendChild(toast);

        // Initialize and show toast
        const bsToast = new bootstrap.Toast(toast, { delay: 3000 });
        bsToast.show();

        // Remove toast after it's hidden
        toast.addEventListener('hidden.bs.toast', () => {
            toast.remove();
        });
    }
}

// Initialize notification manager when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    // Only initialize if user is authenticated (notification bell exists)
    if (document.getElementById('notificationBell')) {
        window.notificationManager = new NotificationManager();
    }
});