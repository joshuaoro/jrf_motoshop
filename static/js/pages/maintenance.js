/**
 * Maintenance page: log/edit/delete maintenance record modal and delete
 * confirmation. Previously an inline <script> block plus onclick=
 * attributes; moved out and switched to event delegation because the
 * production CSP has no 'unsafe-inline' in script-src.
 */
(function () {
    'use strict';

    let deleteTargetId = null;

    function showError(message) {
        const box = document.getElementById('logError');
        box.textContent = message;
        box.classList.remove('hidden');
    }

    function openLogModal() {
        document.getElementById('logError').classList.add('hidden');
        document.getElementById('logModalTitle').textContent = 'Log Maintenance';
        document.getElementById('logForm').reset();
        document.getElementById('logId').value = '';
        document.getElementById('logModal').classList.remove('hidden');
    }

    function editLog(button) {
        document.getElementById('logError').classList.add('hidden');
        const log = JSON.parse(button.getAttribute('data-log'));

        document.getElementById('logModalTitle').textContent = 'Edit Maintenance Record';
        document.getElementById('logId').value = log.id;
        document.getElementById('logEquipment').value = log.equipment_name || '';
        document.getElementById('logSerial').value = log.equipment_serial || '';
        document.getElementById('logType').value = log.maintenance_type;
        document.getElementById('logCost').value = log.cost;
        document.getElementById('logDescription').value = log.description || '';
        document.getElementById('logDate').value =
            log.maintenance_date ? log.maintenance_date.slice(0, 10) : '';
        document.getElementById('logNext').value =
            log.next_maintenance ? log.next_maintenance.slice(0, 10) : '';
        document.getElementById('logPerformedBy').value = log.performed_by || '';
        document.getElementById('logVendor').value = log.vendor || '';
        document.getElementById('logPart').value = log.part_id || '';
        document.getElementById('logNotes').value = log.notes || '';
        document.getElementById('logModal').classList.remove('hidden');
    }

    function closeLogModal() {
        document.getElementById('logModal').classList.add('hidden');
    }

    function askDelete(button) {
        deleteTargetId = button.getAttribute('data-log-id');
        document.getElementById('deleteModal').classList.remove('hidden');
    }

    function closeDeleteModal() {
        document.getElementById('deleteModal').classList.add('hidden');
        deleteTargetId = null;
    }

    async function confirmDelete() {
        if (!deleteTargetId) return;
        try {
            const response = await fetch(`/api/maintenance/${deleteTargetId}`, {
                method: 'DELETE',
                credentials: 'same-origin',
            });
            if (!response.ok) {
                const body = await response.json().catch(() => null);
                alert(JRF.errorMessage(body, 'Could not delete the record.'));
                return;
            }
            // Drain the body before navigating. fetch() resolves on response
            // *headers*, so reloading here tears the page down mid-response
            // and the browser aborts the still-open request.
            await response.json().catch(() => null);
            location.reload();
        } catch (error) {
            console.error(error);
            alert('Could not reach the server.');
        }
    }

    document.addEventListener('click', function (event) {
        if (event.target.closest('.js-open-log-modal')) {
            openLogModal();
            return;
        }
        if (event.target.closest('.js-close-log-modal')) {
            closeLogModal();
            return;
        }
        const editButton = event.target.closest('.js-edit-log');
        if (editButton) {
            editLog(editButton);
            return;
        }
        const deleteButton = event.target.closest('.js-ask-delete-log');
        if (deleteButton) {
            askDelete(deleteButton);
            return;
        }
        if (event.target.closest('.js-close-delete-modal')) {
            closeDeleteModal();
            return;
        }
        if (event.target.closest('.js-confirm-delete')) {
            confirmDelete();
            return;
        }
    });

    document.getElementById('logForm').addEventListener('submit', async function (event) {
        event.preventDefault();
        document.getElementById('logError').classList.add('hidden');

        const logId = document.getElementById('logId').value;
        const partId = document.getElementById('logPart').value;
        const serviced = document.getElementById('logDate').value;
        const next = document.getElementById('logNext').value;

        const payload = {
            equipment_name: document.getElementById('logEquipment').value,
            equipment_serial: document.getElementById('logSerial').value || null,
            maintenance_type: document.getElementById('logType').value,
            description: document.getElementById('logDescription').value,
            cost: document.getElementById('logCost').value || '0',
            performed_by: document.getElementById('logPerformedBy').value || null,
            vendor: document.getElementById('logVendor').value || null,
            notes: document.getElementById('logNotes').value || null,
            part_id: partId ? parseInt(partId, 10) : null,
        };
        if (serviced) payload.maintenance_date = `${serviced}T00:00:00`;
        if (next) payload.next_maintenance = `${next}T00:00:00`;

        const submit = document.getElementById('logSubmit');
        submit.disabled = true;
        try {
            const response = await fetch(
                logId ? `/api/maintenance/${logId}` : '/api/maintenance',
                {
                    method: logId ? 'PUT' : 'POST',
                    credentials: 'same-origin',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                }
            );
            if (!response.ok) {
                const body = await response.json().catch(() => null);
                showError(JRF.errorMessage(body, 'Could not save the record.'));
                return;
            }
            await response.json().catch(() => null);
            location.reload();
        } catch (error) {
            console.error(error);
            showError('Could not reach the server.');
        } finally {
            submit.disabled = false;
        }
    });
})();
