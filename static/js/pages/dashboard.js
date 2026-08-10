/**
 * Dashboard page: auto-reload every 5 minutes so stats stay fresh even if a
 * shift leaves the page open. Previously an inline <script> block; moved
 * out because the production CSP has no 'unsafe-inline' in script-src.
 */
setTimeout(function () {
    window.location.reload();
}, 5 * 60 * 1000);
