/**
 * Shared layout controller: notification bell dropdown, account menu, mobile
 * sidebar drawer, flash-message dismissal, and sidebar active-link highlight.
 *
 * Previously inline in base_new.html. Moved out so the production CSP (no
 * 'unsafe-inline' in script-src) does not block every page's header/sidebar
 * interactions. The notification list used to be rendered server-side by
 * Jinja (which auto-escapes); now it is built here from JSON, so every
 * user-supplied field is run through JRF.escapeHtml / JRF.safeUrl exactly
 * like the other client-side renderers in this codebase (see realtime.js).
 */
(function () {
    'use strict';

    // ------------------------------------------------------------------
    // Flash messages
    // ------------------------------------------------------------------
    document.addEventListener('click', function (event) {
        const dismiss = event.target.closest('.js-dismiss-flash');
        if (dismiss) {
            const message = dismiss.closest('.js-flash-message');
            if (message) message.style.display = 'none';
        }
    });

    // ------------------------------------------------------------------
    // Notification bell dropdown
    // ------------------------------------------------------------------
    let notificationsOpen = false;

    function bellData() {
        const el = document.getElementById('notification-bell-data');
        if (!el) return { unread: 0, recent: [] };
        try {
            return JSON.parse(el.textContent);
        } catch (error) {
            console.error('Could not parse notification bell data:', error);
            return { unread: 0, recent: [] };
        }
    }

    function notificationIconClass(type) {
        if (type === 'success') return 'fas fa-check-circle text-green-500';
        if (type === 'warning') return 'fas fa-exclamation-triangle text-yellow-500';
        if (type === 'error') return 'fas fa-times-circle text-red-500';
        return 'fas fa-info-circle text-blue-500';
    }

    function renderNotificationItem(notification) {
        const esc = JRF.escapeHtml;
        const href = JRF.safeUrl(notification.action_url);
        const link = href
            ? `<a href="${esc(href)}" data-mark-read="${esc(notification.id)}"
                  class="text-xs text-blue-600 hover:text-blue-800">
                   ${esc(notification.action_text || 'View')}
               </a>`
            : '';
        const closeButton = notification.is_read
            ? ''
            : `<button data-mark-read="${esc(notification.id)}" class="ml-2 text-gray-400 hover:text-gray-600">
                   <i class="fas fa-times text-xs"></i>
               </button>`;

        return `
            <div class="p-4 hover:bg-gray-50 border-b border-gray-100 ${notification.is_read ? '' : 'bg-blue-50'}"
                 data-notification-id="${esc(notification.id)}">
                <div class="flex items-start">
                    <div class="flex-shrink-0 mr-3">
                        <i class="${notificationIconClass(notification.type)}"></i>
                    </div>
                    <div class="flex-1 min-w-0">
                        <p class="text-sm font-medium text-gray-900 ${notification.is_read ? '' : 'font-semibold'}">
                            ${esc(notification.title)}
                        </p>
                        <p class="text-sm text-gray-600 mt-1">${esc(notification.message)}</p>
                        <div class="flex items-center justify-between mt-2">
                            <p class="text-xs text-gray-400">${esc(notification.time_ago)}</p>
                            ${link}
                        </div>
                    </div>
                    ${closeButton}
                </div>
            </div>`;
    }

    function renderDropdownContent(data) {
        const markAllButton = data.unread > 0
            ? '<button id="mark-all-notifications-read" class="text-xs text-blue-600 hover:text-blue-800">Mark all read</button>'
            : '';

        const list = data.recent.length
            ? data.recent.map(renderNotificationItem).join('')
            : `<div class="p-8 text-center">
                   <i class="fas fa-bell text-gray-300 text-3xl mb-2"></i>
                   <p class="text-sm text-gray-500">No notifications</p>
               </div>`;

        const footer = data.recent.length
            ? `<div class="p-3 border-t border-gray-200">
                   <a href="/notifications" class="block w-full text-center text-sm text-blue-600 hover:text-blue-800">
                       View all notifications
                   </a>
               </div>`
            : '';

        return `
            <div class="p-4 border-b border-gray-200">
                <div class="flex justify-between items-center">
                    <h3 class="text-sm font-semibold text-gray-800">Notifications</h3>
                    ${markAllButton}
                </div>
            </div>
            <div class="max-h-64 overflow-y-auto">${list}</div>
            ${footer}`;
    }

    function openNotifications(button) {
        const portal = document.getElementById('notification-portal');
        const rect = button.getBoundingClientRect();

        const backdrop = document.createElement('div');
        backdrop.className = 'notification-backdrop';
        backdrop.style.opacity = '0';

        const dropdown = document.createElement('div');
        dropdown.className = 'notification-dropdown';
        dropdown.style.opacity = '0';
        dropdown.style.transform = 'scale(0.95)';
        dropdown.style.top = (rect.bottom + 8) + 'px';
        dropdown.style.right = (window.innerWidth - rect.right) + 'px';
        dropdown.style.width = '320px';
        dropdown.style.maxHeight = '400px';
        dropdown.style.overflow = 'auto';
        dropdown.innerHTML = renderDropdownContent(bellData());

        portal.appendChild(backdrop);
        portal.appendChild(dropdown);

        requestAnimationFrame(function () {
            backdrop.style.transition = 'opacity 0.3s ease';
            dropdown.style.transition = 'opacity 0.2s ease, transform 0.2s ease';
            backdrop.style.opacity = '1';
            dropdown.style.opacity = '1';
            dropdown.style.transform = 'scale(1)';
        });

        notificationsOpen = true;
    }

    function closeNotifications() {
        const portal = document.getElementById('notification-portal');
        const backdrop = portal.querySelector('.notification-backdrop');
        const dropdown = portal.querySelector('.notification-dropdown');

        if (backdrop && dropdown) {
            backdrop.style.opacity = '0';
            dropdown.style.opacity = '0';
            dropdown.style.transform = 'scale(0.95)';

            setTimeout(function () {
                if (backdrop.parentNode) backdrop.parentNode.removeChild(backdrop);
                if (dropdown.parentNode) dropdown.parentNode.removeChild(dropdown);
            }, 200);
        }

        notificationsOpen = false;
    }

    function toggleNotifications(button) {
        if (notificationsOpen) {
            closeNotifications();
        } else {
            openNotifications(button);
        }
    }

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

    async function markNotificationRead(notificationId) {
        const result = await JRF.api(`/api/notifications/${parseInt(notificationId, 10)}/read`, {
            method: 'POST',
        });
        if (!result.ok) return;

        const element = document.querySelector(`[data-notification-id="${notificationId}"]`);
        if (element) {
            element.classList.remove('bg-blue-50');
            const bold = element.querySelector('.font-semibold');
            if (bold) bold.classList.remove('font-semibold');
            const closeButton = element.querySelector('[data-mark-read]');
            if (closeButton) closeButton.remove();
        }

        updateUnreadCount(result.data.unread_count);
    }

    async function markAllNotificationsRead() {
        const result = await JRF.api('/api/notifications/mark-all-read', { method: 'POST' });
        if (!result.ok) return;

        document.querySelectorAll('[data-notification-id]').forEach(function (element) {
            element.classList.remove('bg-blue-50');
            const bold = element.querySelector('.font-semibold');
            if (bold) bold.classList.remove('font-semibold');
        });

        updateUnreadCount(0);

        const markAllButton = document.getElementById('mark-all-notifications-read');
        if (markAllButton) markAllButton.style.display = 'none';
    }

    document.addEventListener('click', function (event) {
        const bellButton = event.target.closest('#notification-bell-button');
        if (bellButton) {
            toggleNotifications(bellButton);
            return;
        }

        const markAll = event.target.closest('#mark-all-notifications-read');
        if (markAll) {
            markAllNotificationsRead();
            return;
        }

        const markOne = event.target.closest('[data-mark-read]');
        if (markOne) {
            markNotificationRead(markOne.dataset.markRead);
            return;
        }

        if (
            notificationsOpen &&
            !event.target.closest('.notification-container') &&
            !event.target.closest('.notification-dropdown')
        ) {
            closeNotifications();
        }
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && notificationsOpen) closeNotifications();
    });

    // Auto-refresh the unread count every 30 seconds.
    setInterval(async function () {
        const result = await JRF.api('/api/notifications/unread-count');
        if (result.ok) updateUnreadCount(result.data.unread_count);
    }, 30000);

    // ------------------------------------------------------------------
    // Account menu + mobile sidebar drawer
    // ------------------------------------------------------------------
    document.addEventListener('DOMContentLoaded', function () {
        const btn = document.getElementById('user-menu-button');
        const menu = document.getElementById('user-menu');

        if (btn && menu) {
            const chevron = btn.querySelector('[data-profile-chevron]');

            function setOpen(open) {
                menu.hidden = !open;
                btn.setAttribute('aria-expanded', open ? 'true' : 'false');
                if (chevron) chevron.style.transform = open ? 'rotate(180deg)' : '';
            }

            setOpen(false);

            btn.addEventListener('click', function (e) {
                e.stopPropagation();
                setOpen(menu.hidden);
            });

            document.addEventListener('click', function (e) {
                if (!menu.hidden && !e.target.closest('.profile-menu')) setOpen(false);
            });

            document.addEventListener('keydown', function (e) {
                if (e.key === 'Escape' && !menu.hidden) {
                    setOpen(false);
                    btn.focus();
                }
            });

            menu.addEventListener('click', function (e) {
                if (e.target.closest('[data-close-profile-menu]')) setOpen(false);
            });
        }

        const sideBar = document.getElementById('sidebar');
        const sideToggle = document.getElementById('sidebar-toggle');
        if (sideBar && sideToggle) {
            function setSidebar(open) {
                sideBar.classList.toggle('sidebar-open', open);
                sideToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
            }
            sideToggle.addEventListener('click', function (e) {
                e.stopPropagation();
                setSidebar(!sideBar.classList.contains('sidebar-open'));
            });
            document.addEventListener('click', function (e) {
                if (
                    sideBar.classList.contains('sidebar-open') &&
                    !e.target.closest('#sidebar') &&
                    !e.target.closest('#sidebar-toggle')
                ) {
                    setSidebar(false);
                }
            });
            document.addEventListener('keydown', function (e) {
                if (e.key === 'Escape' && sideBar.classList.contains('sidebar-open')) setSidebar(false);
            });
        }

        // Highlight the current page in the sidebar.
        const currentPath = window.location.pathname;
        document.querySelectorAll('.sidebar-link').forEach(function (link) {
            link.classList.remove('active');
            const href = link.getAttribute('href');
            if (
                href === currentPath ||
                (currentPath === '/' && href === '/dashboard') ||
                (href !== '/' && currentPath.startsWith(href))
            ) {
                link.classList.add('active');
            }
        });
    });
})();
