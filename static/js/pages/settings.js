/**
 * Settings page: section navigation, per-section change tracking, export /
 * import / reset / backup actions, and the change-password modal.
 *
 * Previously inline in settings.html (44 onclick=/onchange=/onsubmit=
 * attributes plus an inline <script> block) - all blocked outright under
 * the production CSP, which has no 'unsafe-inline' in script-src. Rebuilt
 * here with delegated listeners: one 'click' listener for every button
 * (matched by a js-* marker class), one 'change' listener for the
 * data-mark-section inputs and the import file picker, and one 'submit'
 * listener for the change-password form.
 */
(function () {
    'use strict';

    // Global variables
    let changedSections = new Set();
    let currentSection = 'general';

    // Section navigation
    function showSection(section) {
        // Hide all sections
        document.querySelectorAll('.settings-section').forEach(function (el) {
            el.classList.add('hidden');
        });

        // Remove active state from all nav buttons
        document.querySelectorAll('.settings-nav-btn').forEach(function (btn) {
            btn.classList.remove('bg-blue-50', 'text-blue-600');
        });

        // Show selected section
        const targetSection = document.getElementById(section + '-section');
        if (targetSection) {
            targetSection.classList.remove('hidden');
        }

        // Add active state to the matching nav button
        const activeBtn = document.querySelector(`.js-show-section[data-section="${section}"]`);
        if (activeBtn) {
            activeBtn.classList.add('bg-blue-50', 'text-blue-600');
        }

        currentSection = section;
    }

    // Mark section as changed
    function markSectionAsChanged(section) {
        changedSections.add(section);
    }

    // Collect settings from a section
    function collectSectionSettings(section) {
        const settings = {};
        const sectionElement = document.getElementById(section + '-section');

        if (!sectionElement) return settings;

        // Collect all inputs in the section
        const inputs = sectionElement.querySelectorAll('input, select, textarea');
        inputs.forEach(function (input) {
            const key = input.id.replace(section + '-', '');
            if (input.type === 'checkbox') {
                settings[key] = input.checked ? 'true' : 'false'; // Convert boolean to string
            } else if (input.type === 'number') {
                settings[key] = parseFloat(input.value) || 0;
            } else {
                settings[key] = input.value;
            }
        });

        return settings;
    }

    const SETTING_SECTIONS =
        ['general', 'inventory', 'sales', 'notifications', 'backup', 'security'];

    // Save all settings
    async function saveAllSettings() {
        const payload = {};
        SETTING_SECTIONS.forEach(function (section) {
            payload[section] = collectSectionSettings(section);
        });

        const result = await JRF.api('/api/settings', { method: 'POST', body: payload });
        if (!result.ok) {
            JRF.notifyError(result, 'Failed to save settings.');
            return;
        }

        changedSections.clear();
        const updated = (result.data && result.data.updated) || [];
        const errors = (result.data && result.data.errors) || [];
        JRF.notify(`Saved ${updated.length} setting(s).`, 'success');
        // Partial success is reported, not silently swallowed.
        if (errors.length) JRF.notify(errors.join('  |  '), 'warning');
    }

    // Export settings
    async function exportSettings() {
        const result = await JRF.api('/api/settings/export');
        if (!result.ok) {
            JRF.notifyError(result, 'Failed to export settings.');
            return;
        }

        const blob = new Blob([JSON.stringify(result.data, null, 2)], {
            type: 'application/json',
        });
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `settings_export_${new Date().toISOString().split('T')[0]}.json`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);

        JRF.notify('Settings exported.', 'success');
    }

    // Import settings
    async function importSettings(event) {
        const file = event.target.files[0];
        if (!file) return;

        const formData = new FormData();
        formData.append('file', file);

        const result = await JRF.api('/api/settings/import', {
            method: 'POST',
            body: formData,
        });
        event.target.value = '';

        if (!result.ok) {
            JRF.notifyError(result, 'Failed to import settings.');
            return;
        }

        JRF.notify('Settings imported. Reloading…', 'success');
        setTimeout(function () { window.location.reload(); }, 1500);
    }

    // Reset settings
    async function resetSettings() {
        if (!confirm('Reset all settings to defaults? This cannot be undone.')) return;

        const result = await JRF.api('/api/settings/reset', { method: 'POST' });
        if (!result.ok) {
            JRF.notifyError(result, 'Failed to reset settings.');
            return;
        }

        JRF.notify('Settings reset to defaults. Reloading…', 'success');
        setTimeout(function () { window.location.reload(); }, 1000);
    }

    // Create backup
    async function createBackup() {
        JRF.notify('Starting backup…', 'info');
        const result = await JRF.api('/api/system/backups', { method: 'POST' });
        if (!result.ok) {
            JRF.notifyError(result, 'Backup failed.');
            return;
        }

        JRF.notify('Backup created. Reloading…', 'success');
        setTimeout(function () { window.location.reload(); }, 1000);
    }

    // Restore is deliberately not wired up: there is no restore endpoint, and
    // a half-built one on this screen would be the most dangerous button here.
    function restoreBackup() {
        JRF.notify(
            'Restore is not available yet. Use pg_restore against a downloaded backup.',
            'warning'
        );
    }

    // Change password modal
    function openChangePasswordModal() {
        document.getElementById('changePasswordModal').classList.remove('hidden');
        document.getElementById('cp-current').focus();
    }

    function closeChangePasswordModal() {
        document.getElementById('changePasswordModal').classList.add('hidden');
        document.getElementById('changePasswordForm').reset();
    }

    async function submitChangePassword(event) {
        event.preventDefault();

        const current_password = document.getElementById('cp-current').value;
        const new_password = document.getElementById('cp-new').value;
        const confirm_password = document.getElementById('cp-confirm').value;

        if (new_password !== confirm_password) {
            JRF.notify('New passwords do not match.', 'error');
            return;
        }

        const result = await JRF.api('/api/auth/change-password', {
            method: 'POST',
            body: { current_password: current_password, new_password: new_password },
        });

        if (!result.ok) {
            JRF.notifyError(result, 'Could not change password.');
            return;
        }

        closeChangePasswordModal();
        JRF.notify('Password changed successfully.', 'success');
    }

    // Test database connection (not currently wired to a button, kept for
    // parity with the original inline script).
    async function testConnection() {
        const result = await JRF.api('/health');
        const healthy = result.ok && result.data && result.data.database === 'connected';
        JRF.notify(
            healthy ? 'Database connection successful.' : 'Database connection failed.',
            healthy ? 'success' : 'error'
        );
    }
    void testConnection;

    // ------------------------------------------------------------------
    // Delegated event wiring
    // ------------------------------------------------------------------
    document.addEventListener('click', function (event) {
        const navBtn = event.target.closest('.js-show-section');
        if (navBtn) {
            showSection(navBtn.dataset.section);
            return;
        }
        if (event.target.closest('.js-export-settings')) {
            exportSettings();
            return;
        }
        if (event.target.closest('.js-reset-settings')) {
            resetSettings();
            return;
        }
        if (event.target.closest('.js-save-all-settings')) {
            saveAllSettings();
            return;
        }
        if (event.target.closest('.js-create-backup')) {
            createBackup();
            return;
        }
        if (event.target.closest('.js-restore-backup')) {
            restoreBackup();
            return;
        }
        if (event.target.closest('.js-open-change-password-modal')) {
            openChangePasswordModal();
            return;
        }
        if (event.target.closest('.js-close-change-password-modal')) {
            closeChangePasswordModal();
        }
    });

    document.addEventListener('change', function (event) {
        if (event.target.closest('#importFile')) {
            importSettings(event);
            return;
        }
        const marker = event.target.closest('[data-mark-section]');
        if (marker) {
            markSectionAsChanged(marker.dataset.markSection);
        }
    });

    document.addEventListener('submit', function (event) {
        if (event.target.closest('#changePasswordForm')) {
            submitChangePassword(event);
        }
    });

    // Initialize settings: show the general section on load. (The original
    // template registered this same DOMContentLoaded listener twice; one is
    // enough.)
    document.addEventListener('DOMContentLoaded', function () {
        showSection('general');
    });
})();
