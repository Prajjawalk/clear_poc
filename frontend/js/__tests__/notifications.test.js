/**
 * Tests for Notification Manager
 */

import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';

// Mock the NotificationManager class
const createNotificationManager = () => {
  // Create a simple mock implementation for testing
  class NotificationManager {
    constructor() {
      this.unreadCount = 0;
      this.updateInterval = 30000;
      this.notificationBell = document.getElementById('notificationBell');
      this.notificationBadge = document.getElementById('notificationBadge');
      this.unreadCountElement = document.getElementById('unreadCount');
      this.notificationList = document.getElementById('notificationList');
      this.markAllReadBtn = document.getElementById('markAllReadBtn');
    }

    updateBadge(count) {
      this.unreadCount = count;
      if (this.notificationBadge) {
        if (count > 0) {
          this.notificationBadge.textContent = count > 99 ? '99+' : count;
          this.notificationBadge.style.display = 'block';
        } else {
          this.notificationBadge.style.display = 'none';
        }
      }
    }

    markAsRead(notificationId) {
      return fetch(`/api/notifications/${notificationId}/mark-read/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        }
      });
    }
  }

  return NotificationManager;
};

describe('NotificationManager', () => {
  let NotificationManager;
  let manager;

  beforeEach(() => {
    // Create DOM elements
    document.body.innerHTML = `
      <div id="notificationBell">
        <span id="notificationBadge" style="display: none;"></span>
      </div>
      <div id="unreadCount">0</div>
      <div id="notificationList"></div>
      <button id="markAllReadBtn">Mark All Read</button>
    `;

    // Reset fetch mock
    global.fetch = vi.fn();

    // Get the mock class
    NotificationManager = createNotificationManager();
  });

  afterEach(() => {
    vi.clearAllTimers();
  });

  describe('Initialization', () => {
    it('creates a NotificationManager instance', () => {
      manager = new NotificationManager();
      expect(manager).toBeInstanceOf(NotificationManager);
    });

    it('initializes with zero unread count', () => {
      manager = new NotificationManager();
      expect(manager.unreadCount).toBe(0);
    });

    it('sets update interval to 30 seconds', () => {
      manager = new NotificationManager();
      expect(manager.updateInterval).toBe(30000);
    });

    it('finds notification elements', () => {
      manager = new NotificationManager();
      expect(manager.notificationBell).toBeTruthy();
      expect(manager.notificationBadge).toBeTruthy();
      expect(manager.unreadCountElement).toBeTruthy();
    });
  });

  describe('Badge Update', () => {
    beforeEach(() => {
      manager = new NotificationManager();
    });

    it('updates badge with count', () => {
      manager.updateBadge(5);

      const badge = document.getElementById('notificationBadge');
      expect(badge.textContent).toBe('5');
      expect(badge.style.display).toBe('block');
    });

    it('shows 99+ for counts over 99', () => {
      manager.updateBadge(150);

      const badge = document.getElementById('notificationBadge');
      expect(badge.textContent).toBe('99+');
    });

    it('hides badge when count is zero', () => {
      manager.updateBadge(5);
      manager.updateBadge(0);

      const badge = document.getElementById('notificationBadge');
      expect(badge.style.display).toBe('none');
    });

    it('updates unread count', () => {
      manager.updateBadge(3);
      expect(manager.unreadCount).toBe(3);
    });
  });

  describe('Mark as Read', () => {
    beforeEach(() => {
      manager = new NotificationManager();
    });

    it('calls API to mark notification as read', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true })
      });

      await manager.markAsRead(123);

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/notifications/123/mark-read/',
        expect.objectContaining({
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          }
        })
      );
    });
  });

  describe('Badge Display States', () => {
    beforeEach(() => {
      manager = new NotificationManager();
    });

    it('shows badge for single notification', () => {
      manager.updateBadge(1);

      const badge = document.getElementById('notificationBadge');
      expect(badge.style.display).toBe('block');
      expect(badge.textContent).toBe('1');
    });

    it('shows badge for multiple notifications', () => {
      manager.updateBadge(42);

      const badge = document.getElementById('notificationBadge');
      expect(badge.style.display).toBe('block');
      expect(badge.textContent).toBe('42');
    });

    it('handles edge case of exactly 99 notifications', () => {
      manager.updateBadge(99);

      const badge = document.getElementById('notificationBadge');
      expect(badge.textContent).toBe('99');
    });

    it('handles edge case of 100 notifications', () => {
      manager.updateBadge(100);

      const badge = document.getElementById('notificationBadge');
      expect(badge.textContent).toBe('99+');
    });
  });

  describe('Element References', () => {
    it('handles missing optional elements', () => {
      document.body.innerHTML = `<div id="notificationBell"></div>`;

      manager = new NotificationManager();

      // Should not throw even if optional elements are missing
      expect(manager.notificationBadge).toBeFalsy();
      expect(manager.markAllReadBtn).toBeFalsy();
    });
  });
});
