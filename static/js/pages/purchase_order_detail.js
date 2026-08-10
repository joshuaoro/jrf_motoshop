/**
 * Purchase order detail page: status transitions and receiving stock.
 * Previously an inline <script> block plus onclick= attributes, including
 * one generated per status by a Jinja loop; moved out and switched to
 * event delegation (data-status + a shared .js-set-status listener)
 * because the production CSP has no 'unsafe-inline' in script-src.
 */
(function () {
    'use strict';

    const ORDER_ID = parseInt(document.getElementById('purchase-order-data').getAttribute('data-order-id'), 10);

    function showError(message) {
        const box = document.getElementById('pageError');
        box.textContent = message;
        box.classList.remove('hidden');
        document.getElementById('pageOk').classList.add('hidden');
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    function receiveAll() {
        document.querySelectorAll('.receive-qty').forEach(input => {
            input.value = input.getAttribute('data-outstanding');
        });
    }

    async function setStatus(status) {
        try {
            const response = await fetch(`/api/purchase-orders/${ORDER_ID}/status`, {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status: status }),
            });
            if (!response.ok) {
                const body = await response.json().catch(() => null);
                showError(JRF.errorMessage(body, 'Could not change the status.'));
                return;
            }
            // Drain the body before navigating. fetch() resolves on response
            // *headers*, so reloading here tears down the page while the
            // response is still streaming - the browser aborts the request,
            // and whether the server's commit already landed is a race.
            await response.json().catch(() => null);
            location.reload();
        } catch (error) {
            console.error(error);
            showError('Could not reach the server.');
        }
    }

    document.addEventListener('click', function (event) {
        if (event.target.closest('.js-receive-all')) {
            receiveAll();
            return;
        }
        const statusButton = event.target.closest('.js-set-status');
        if (statusButton) {
            setStatus(statusButton.getAttribute('data-status'));
            return;
        }
    });

    const receiveForm = document.getElementById('receiveForm');
    if (receiveForm) {
        receiveForm.addEventListener('submit', async function (event) {
            event.preventDefault();

            const items = [];
            document.querySelectorAll('.receive-qty').forEach(input => {
                const quantity = parseInt(input.value, 10) || 0;
                if (quantity > 0) {
                    items.push({
                        part_id: parseInt(input.getAttribute('data-part-id'), 10),
                        quantity: quantity,
                    });
                }
            });

            if (items.length === 0) {
                showError('Enter a quantity against at least one line before receiving.');
                return;
            }

            const submit = document.getElementById('receiveSubmit');
            submit.disabled = true;
            try {
                const response = await fetch(`/api/purchase-orders/${ORDER_ID}/receive`, {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ items: items }),
                });
                if (!response.ok) {
                    const body = await response.json().catch(() => null);
                    showError(JRF.errorMessage(body, 'Could not receive the items.'));
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
    }
})();
