/**
 * Notifications page: loads the list from the API, renders it client-side,
 * and wires filtering, pagination, mark-read and delete actions.
 *
 * Previously inline in notifications.html - blocked outright under the
 * production CSP (no 'unsafe-inline' in script-src). Converted to delegated
 * listeners keyed on data-* attributes / js-* marker classes instead of
 * inline onclick=/onchange= attributes.
 *
 * Two real bugs were found while converting and are fixed here:
 *
 *  1. `markNotificationRead()` and `markAllNotificationsRead()` were called
 *     from onclick= attributes but were never defined anywhere in this
 *     file - clicking "Mark as read", the action link, or "Mark All Read"
 *     threw a ReferenceError and did nothing. They're implemented below
 *     against the existing `/api/notifications/<id>/read` and
 *     `/api/notifications/mark-all-read` endpoints (see app/api/notifications.py).
 *
 *  2. `updateUnreadCount()` was called after every load/read/delete but was
 *     also never defined in this file. It used to work only because
 *     base_new.html's old inline <script> happened to declare a
 *     same-named function in the shared global scope. Now that the shared
 *     layout script (static/js/pages/base.js) is an IIFE and no longer
 *     leaks that name onto `window`, the call would throw. A local
 *     implementation is defined here that updates the same header bell
 *     badge, mirroring base.js's version.
 */
(function () {
    'use strict';

    let currentPage = 1;
    let currentFilter = 'all';
    let currentCategory = 'all';

    async function loadNotifications(page) {
        page = page || 1;
        currentPage = page;

        const loading = document.getElementById('loading');
        const emptyState = document.getElementById('empty-state');
        const notificationsList = document.getElementById('notifications-list');
        const pagination = document.getElementById('pagination');

        loading.classList.remove('hidden');
        emptyState.classList.add('hidden');
        notificationsList.innerHTML = '';
        pagination.classList.add('hidden');

        try {
            const params = new URLSearchParams({
                page: page,
                per_page: 20,
                unread_only: currentFilter === 'unread' ? 'true' : 'false',
            });

            const response = await fetch(`/api/notifications?${params}`);
            const data = await response.json();

            loading.classList.add('hidden');

            if (data.notifications && data.notifications.length > 0) {
                renderNotifications(data.notifications);
                updatePagination(data);
            } else {
                emptyState.classList.remove('hidden');
            }

            // Update unread count in header
            updateUnreadCount(data.unread_count);
        } catch (error) {
            console.error('Error loading notifications:', error);
            loading.classList.add('hidden');
            notificationsList.innerHTML =
                '<div class="p-8 text-center text-red-500">Error loading notifications</div>';
        }
    }

    function renderNotifications(notifications) {
        const notificationsList = document.getElementById('notifications-list');
        const esc = JRF.escapeHtml;

        notifications.forEach(function (notification) {
            const notificationEl = document.createElement('div');
            notificationEl.className =
                `p-4 border-b border-gray-100 hover:bg-gray-50 ${!notification.is_read ? 'bg-blue-50' : ''}`;
            notificationEl.setAttribute('data-notification-id', notification.id);

            const iconClass = getNotificationIcon(notification.type);
            const iconColor = getNotificationColor(notification.type);

            notificationEl.innerHTML = `
                <div class="flex items-start">
                    <div class="flex-shrink-0 mr-3">
                        <i class="${iconClass} ${iconColor}"></i>
                    </div>
                    <div class="flex-1 min-w-0">
                        <p class="text-sm font-medium text-gray-900 ${!notification.is_read ? 'font-semibold' : ''}">
                            ${esc(notification.title)}
                        </p>
                        <p class="text-sm text-gray-600 mt-1">
                            ${esc(notification.message)}
                        </p>
                        <div class="flex items-center justify-between mt-2">
                            <p class="text-xs text-gray-400">
                                ${esc(notification.time_ago)}
                            </p>
                            <div class="flex space-x-2">
                                ${notification.action_url ? `
                                    <a href="${esc(JRF.safeUrl(notification.action_url) || '#')}"
                                       class="text-xs text-blue-600 hover:text-blue-800"
                                       data-mark-read="${notification.id}">
                                        ${esc(notification.action_text || 'View')}
                                    </a>
                                ` : ''}
                                ${!notification.is_read ? `
                                    <button data-mark-read="${notification.id}"
                                            class="text-xs text-gray-500 hover:text-gray-700">
                                        Mark as read
                                    </button>
                                ` : ''}
                                <button data-delete-notification="${notification.id}"
                                        class="text-xs text-red-500 hover:text-red-700">
                                    Delete
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            `;

            notificationsList.appendChild(notificationEl);
        });
    }

    function getNotificationIcon(type) {
        const icons = {
            success: 'fas fa-check-circle',
            warning: 'fas fa-exclamation-triangle',
            error: 'fas fa-times-circle',
            info: 'fas fa-info-circle',
        };
        return icons[type] || 'fas fa-info-circle';
    }

    function getNotificationColor(type) {
        const colors = {
            success: 'text-green-500',
            warning: 'text-yellow-500',
            error: 'text-red-500',
            info: 'text-blue-500',
        };
        return colors[type] || 'text-blue-500';
    }

    function updatePagination(data) {
        const pagination = document.getElementById('pagination');
        const paginationInfo = document.getElementById('pagination-info');
        const prevPage = document.getElementById('prev-page');
        const nextPage = document.getElementById('next-page');

        if (data.pages > 1) {
            pagination.classList.remove('hidden');
            paginationInfo.textContent = `Page ${data.current_page} of ${data.pages} (${data.total} total)`;

            prevPage.disabled = data.current_page <= 1;
            nextPage.disabled = data.current_page >= data.pages;
        }
    }

    function loadPage(page) {
        loadNotifications(page);
    }

    function filterNotifications() {
        currentFilter = document.getElementById('filter-type').value;
        currentCategory = document.getElementById('filter-category').value;
        loadNotifications(1);
    }

    /**
     * Update the notification bell badge in the shared layout header.
     *
     * Bug fix: this used to rely on a same-named function that base_new.html's
     * old inline <script> declared in the global scope. base.js (the CSP
     * conversion of that script) wraps everything in an IIFE and no longer
     * leaks it, so a call here would otherwise throw ReferenceError on every
     * load/read/delete. Reimplemented locally, mirroring base.js's version.
     */
    function updateUnreadCount(count) {
        const bell = document.getElementById('notification-bell-button');
        if (!bell) return;
        let badge = bell.querySelector('span');

        if (count > 0) {
            if (!badge) {
                badge = document.createElement('span');
                badge.className =
                    'absolute -top-1 -right-1 h-5 w-5 rounded-full bg-red-500 text-white text-xs ' +
                    'flex items-center justify-center animate-pulse';
                bell.appendChild(badge);
            }
            badge.textContent = String(count);
            badge.style.display = 'flex';
        } else if (badge) {
            badge.style.display = 'none';
        }
    }

    /**
     * Bug fix: called from the "Mark as read" button and the notification's
     * action link, but never defined - both were dead (ReferenceError).
     */
    async function markNotificationRead(notificationId) {
        try {
            const response = await fetch(`/api/notifications/${notificationId}/read`, {
                method: 'POST',
            });
            if (!response.ok) return;
            const data = await response.json();

            const notificationEl = document.querySelector(
                `[data-notification-id="${notificationId}"]`
            );
            if (notificationEl) {
                notificationEl.classList.remove('bg-blue-50');
                const boldText = notificationEl.querySelector('.font-semibold');
                if (boldText) boldText.classList.remove('font-semibold');
                const markReadButton = notificationEl.querySelector('button[data-mark-read]');
                if (markReadButton) markReadButton.remove();
            }

            updateUnreadCount(data.unread_count);
        } catch (error) {
            console.error('Error marking notification as read:', error);
        }
    }

    /** Bug fix: called from the "Mark All Read" button, but never defined. */
    async function markAllNotificationsRead() {
        try {
            const response = await fetch('/api/notifications/mark-all-read', {
                method: 'POST',
            });
            if (!response.ok) return;

            const markAllButton = document.querySelector('.js-mark-all-read');
            if (markAllButton) markAllButton.classList.add('hidden');

            loadNotifications(currentPage);
        } catch (error) {
            console.error('Error marking all notifications as read:', error);
        }
    }

    async function deleteNotification(notificationId) {
        if (!confirm('Are you sure you want to delete this notification?')) {
            return;
        }

        try {
            const response = await fetch(`/api/notifications/${notificationId}`, {
                method: 'DELETE',
            });

            if (response.ok) {
                const data = await response.json();

                // Remove from UI
                const notificationEl = document.querySelector(
                    `[data-notification-id="${notificationId}"]`
                );
                if (notificationEl) {
                    notificationEl.remove();
                }

                // Update unread count
                updateUnreadCount(data.unread_count);

                // Reload if no more notifications
                if (document.querySelectorAll('[data-notification-id]').length === 0) {
                    loadNotifications();
                }
            }
        } catch (error) {
            console.error('Error deleting notification:', error);
        }
    }

    async function clearAllNotifications() {
        if (!confirm('Are you sure you want to clear all notifications? This action cannot be undone.')) {
            return;
        }

        try {
            const response = await fetch('/api/notifications/clear-all', {
                method: 'DELETE',
            });

            if (response.ok) {
                loadNotifications();
            }
        } catch (error) {
            console.error('Error clearing notifications:', error);
        }
    }

    // ------------------------------------------------------------------
    // Delegated event wiring
    // ------------------------------------------------------------------
    document.addEventListener('click', function (event) {
        if (event.target.closest('.js-mark-all-read')) {
            markAllNotificationsRead();
            return;
        }
        if (event.target.closest('.js-clear-all')) {
            clearAllNotifications();
            return;
        }
        if (event.target.closest('#prev-page')) {
            loadPage(currentPage - 1);
            return;
        }
        if (event.target.closest('#next-page')) {
            loadPage(currentPage + 1);
            return;
        }
        const markReadTarget = event.target.closest('[data-mark-read]');
        if (markReadTarget) {
            markNotificationRead(parseInt(markReadTarget.dataset.markRead, 10));
            return;
        }
        const deleteTarget = event.target.closest('[data-delete-notification]');
        if (deleteTarget) {
            deleteNotification(parseInt(deleteTarget.dataset.deleteNotification, 10));
        }
    });

    document.addEventListener('change', function (event) {
        if (event.target.closest('#filter-type') || event.target.closest('#filter-category')) {
            filterNotifications();
        }
    });

    document.addEventListener('DOMContentLoaded', function () {
        loadNotifications();
    });
})();
