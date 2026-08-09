/**
 * Shared front-end helpers.
 *
 * Every page used to hand-roll the same fetch/parse/branch block, and each
 * copy got the details slightly wrong: branching on a `success` field the
 * endpoint did not return, reading `data.message` when errors carried
 * `error`, or ignoring the status code entirely so a 403 looked like a
 * success. This module is the one implementation.
 *
 * Loaded by base_new.html, so `JRF` is available on every page.
 */
(function (window) {
    'use strict';

    const JRF = {};

    // ------------------------------------------------------------------
    // Escaping
    // ------------------------------------------------------------------

    /** Escape text destined for innerHTML. */
    JRF.escapeHtml = function (value) {
        if (value === null || value === undefined) return '';
        return String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    };

    /**
     * Vet a URL destined for an href.
     * Escaping alone would still allow `javascript:` and `data:`, so only
     * same-origin paths are accepted.
     */
    JRF.safeUrl = function (value) {
        if (!value) return null;
        const url = String(value).trim();
        if (!url.startsWith('/') || url.startsWith('//')) return null;
        return url;
    };

    // ------------------------------------------------------------------
    // HTTP
    // ------------------------------------------------------------------

    /** The CSRF token rendered into the page head by base_new.html. */
    JRF.csrfToken = function () {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : null;
    };

    /**
     * Turn an error payload into one readable line.
     * Handles marshmallow's {details: {field: [messages]}} shape.
     */
    JRF.errorMessage = function (payload, fallback) {
        fallback = fallback || 'Something went wrong.';
        if (!payload) return fallback;

        if (payload.details && typeof payload.details === 'object') {
            const parts = Object.entries(payload.details).map(function (entry) {
                const messages = entry[1];
                return entry[0] + ': ' +
                    (Array.isArray(messages) ? messages.join(' ') : messages);
            });
            if (parts.length) return parts.join('  |  ');
        }
        return payload.error || payload.message || fallback;
    };

    /**
     * Call the JSON API.
     *
     * Always resolves to { ok, status, data } - it never throws for an HTTP
     * error, so callers branch on `ok` rather than wrapping every call in
     * try/catch. A 401 redirects to the login page, because every other
     * outcome of an expired session is a confusing error message.
     */
    JRF.api = async function (url, options) {
        options = options || {};
        const method = (options.method || 'GET').toUpperCase();

        const headers = Object.assign({}, options.headers);
        if (options.body !== undefined && !(options.body instanceof FormData)) {
            headers['Content-Type'] = headers['Content-Type'] || 'application/json';
        }
        // Harmless for the API blueprints (CSRF-exempt), needed if a call is
        // ever pointed at a form endpoint.
        if (method !== 'GET' && method !== 'HEAD') {
            const token = JRF.csrfToken();
            if (token) headers['X-CSRFToken'] = token;
        }

        let body = options.body;
        if (body !== undefined && !(body instanceof FormData) && typeof body !== 'string') {
            body = JSON.stringify(body);
        }

        let response;
        try {
            response = await window.fetch(url, {
                method: method,
                credentials: 'same-origin',
                headers: headers,
                body: body,
            });
        } catch (networkError) {
            console.error('Network error calling ' + url, networkError);
            return {
                ok: false,
                status: 0,
                data: { error: 'Could not reach the server. Check your connection.' },
            };
        }

        if (response.status === 401) {
            window.location.href =
                '/login?next=' + encodeURIComponent(window.location.pathname);
            return { ok: false, status: 401, data: { error: 'Session expired.' } };
        }

        let data = null;
        if (response.status !== 204) {
            data = await response.json().catch(function () { return null; });
        }

        return { ok: response.ok, status: response.status, data: data };
    };

    // ------------------------------------------------------------------
    // Feedback
    // ------------------------------------------------------------------
    const TOAST_STYLES = {
        success: { bg: 'bg-green-600', icon: 'fa-circle-check' },
        error: { bg: 'bg-red-600', icon: 'fa-circle-exclamation' },
        warning: { bg: 'bg-yellow-500', icon: 'fa-triangle-exclamation' },
        info: { bg: 'bg-blue-600', icon: 'fa-circle-info' },
    };

    function toastContainer() {
        let container = document.getElementById('jrfToasts');
        if (!container) {
            container = document.createElement('div');
            container.id = 'jrfToasts';
            container.className = 'fixed top-4 right-4 z-[100] space-y-2 w-80 max-w-[90vw]';
            document.body.appendChild(container);
        }
        return container;
    }

    /** Non-blocking replacement for alert(). */
    JRF.notify = function (message, type, timeout) {
        const style = TOAST_STYLES[type] || TOAST_STYLES.info;
        const toast = document.createElement('div');
        toast.className =
            style.bg + ' text-white px-4 py-3 rounded-lg shadow-lg flex items-start gap-3 ' +
            'transition-opacity duration-300';
        toast.setAttribute('role', type === 'error' ? 'alert' : 'status');
        toast.innerHTML =
            '<i class="fas ' + style.icon + ' mt-0.5"></i>' +
            '<span class="flex-1 text-sm">' + JRF.escapeHtml(message) + '</span>' +
            '<button type="button" class="opacity-70 hover:opacity-100" aria-label="Dismiss">' +
            '<i class="fas fa-times"></i></button>';

        function dismiss() {
            toast.style.opacity = '0';
            setTimeout(function () { toast.remove(); }, 300);
        }
        toast.querySelector('button').addEventListener('click', dismiss);

        toastContainer().appendChild(toast);
        setTimeout(dismiss, timeout || (type === 'error' ? 7000 : 4000));
        return toast;
    };

    /** Report a failed JRF.api() result. */
    JRF.notifyError = function (result, fallback) {
        JRF.notify(JRF.errorMessage(result && result.data, fallback), 'error');
    };

    // ------------------------------------------------------------------
    // Modals
    // ------------------------------------------------------------------
    JRF.openModal = function (id) {
        const modal = document.getElementById(id);
        if (modal) modal.classList.remove('hidden');
    };

    JRF.closeModal = function (id) {
        const modal = document.getElementById(id);
        if (modal) modal.classList.add('hidden');
    };

    /** Close the topmost open modal when Escape is pressed. */
    document.addEventListener('keydown', function (event) {
        if (event.key !== 'Escape') return;
        const open = Array.from(document.querySelectorAll('[id$="Modal"]'))
            .filter(function (element) { return !element.classList.contains('hidden'); });
        if (open.length) open[open.length - 1].classList.add('hidden');
    });

    // ------------------------------------------------------------------
    // Formatting
    // ------------------------------------------------------------------
    JRF.currency = function (amount, symbol) {
        const value = Number(amount);
        return (symbol || '₱') + (isFinite(value) ? value : 0).toLocaleString(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    };

    window.JRF = JRF;

    // Back-compat aliases: templates call these bare names directly.
    window.escapeHtml = JRF.escapeHtml;
    window.safeUrl = JRF.safeUrl;
})(window);
