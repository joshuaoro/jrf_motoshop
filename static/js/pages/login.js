/**
 * Login page: Tailwind CDN brand color config, and the show/hide password
 * toggle. Previously two inline <script> blocks; moved out because the
 * production CSP has no 'unsafe-inline' in script-src.
 */
// Guarded: if the Tailwind CDN script hasn't loaded yet (slow network, or
// blocked outright as the browser test suite does deliberately), `tailwind`
// is undefined and an unguarded assignment throws a ReferenceError.
if (window.tailwind) {
    window.tailwind.config = {
        theme: {
            extend: {
                colors: {
                    brand: { 600: '#2563eb', 700: '#1d4ed8', 800: '#1e40af' },
                },
            },
        },
    };
}

document.addEventListener('DOMContentLoaded', function () {
    const pw = document.getElementById('password');
    const btn = document.getElementById('toggle-password');
    btn.addEventListener('click', function () {
        const show = pw.type === 'password';
        pw.type = show ? 'text' : 'password';
        btn.textContent = show ? 'Hide' : 'Show';
    });
});
