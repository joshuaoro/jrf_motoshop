/**
 * Purchase orders page: new-order modal with dynamic line-item rows.
 * Previously an inline <script> block plus onclick=/onchange=/oninput=
 * attributes - including inside a JS template literal that generated new
 * rows with their own inline handlers. Moved out and switched to event
 * delegation because the production CSP has no 'unsafe-inline' in
 * script-src, which blocks both inline <script> blocks and inline
 * on*= attributes, even on markup injected via innerHTML.
 */
(function () {
    'use strict';

    const PARTS = JSON.parse(document.getElementById('purchase-orders-data').textContent);

    function showError(message) {
        const box = document.getElementById('orderError');
        box.textContent = message;
        box.classList.remove('hidden');
    }

    function openOrderModal() {
        document.getElementById('orderError').classList.add('hidden');
        document.getElementById('orderForm').reset();
        document.getElementById('lineItems').innerHTML = '';
        addLine();
        recalculate();
        document.getElementById('orderModal').classList.remove('hidden');
    }

    function closeOrderModal() {
        document.getElementById('orderModal').classList.add('hidden');
    }

    function addLine() {
        const row = document.createElement('tr');
        row.className = 'border-t line-row';

        const options = ['<option value="">Select a part…</option>']
            .concat(PARTS.map(part =>
                `<option value="${part.id}" data-cost="${part.cost_price}">` +
                `${escapeHtml(part.name)}${part.sku ? ' (' + escapeHtml(part.sku) + ')' : ''}</option>`))
            .join('');

        row.innerHTML = `
            <td class="px-3 py-2">
                <select class="line-part w-full px-2 py-1 border rounded">${options}</select>
            </td>
            <td class="px-3 py-2">
                <input type="number" class="line-qty w-full px-2 py-1 border rounded" min="1" value="1">
            </td>
            <td class="px-3 py-2">
                <input type="number" class="line-cost w-full px-2 py-1 border rounded" min="0" step="0.01" value="0.00">
            </td>
            <td class="px-3 py-2 text-right line-total text-gray-700">₱0.00</td>
            <td class="px-3 py-2 text-center">
                <button type="button" class="js-remove-line text-red-500 hover:text-red-700" title="Remove line">
                    <i class="fas fa-times"></i>
                </button>
            </td>`;

        document.getElementById('lineItems').appendChild(row);
    }

    function removeLine(button) {
        const rows = document.querySelectorAll('.line-row');
        if (rows.length <= 1) {
            showError('An order needs at least one line item.');
            return;
        }
        button.closest('tr').remove();
        recalculate();
    }

    /** Prefill the unit cost from what the part last cost. */
    function partChanged(select) {
        const option = select.options[select.selectedIndex];
        const cost = option ? option.getAttribute('data-cost') : null;
        if (cost) {
            select.closest('tr').querySelector('.line-cost').value = Number(cost).toFixed(2);
        }
        recalculate();
    }

    function recalculate() {
        let total = 0;
        document.querySelectorAll('.line-row').forEach(row => {
            const qty = parseInt(row.querySelector('.line-qty').value, 10) || 0;
            const cost = parseFloat(row.querySelector('.line-cost').value) || 0;
            const lineTotal = qty * cost;
            total += lineTotal;
            row.querySelector('.line-total').textContent =
                '₱' + lineTotal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        });
        total += parseFloat(document.getElementById('orderShipping').value) || 0;
        document.getElementById('orderTotal').textContent =
            '₱' + total.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    document.addEventListener('click', function (event) {
        if (event.target.closest('.js-open-order-modal')) {
            openOrderModal();
            return;
        }
        if (event.target.closest('.js-close-order-modal')) {
            closeOrderModal();
            return;
        }
        if (event.target.closest('.js-add-line')) {
            addLine();
            return;
        }
        const removeButton = event.target.closest('.js-remove-line');
        if (removeButton) {
            removeLine(removeButton);
            return;
        }
    });

    document.addEventListener('change', function (event) {
        const partSelect = event.target.closest('.line-part');
        if (partSelect) {
            partChanged(partSelect);
        }
    });

    document.addEventListener('input', function (event) {
        if (
            event.target.closest('.line-qty') ||
            event.target.closest('.line-cost') ||
            event.target.closest('#orderShipping')
        ) {
            recalculate();
        }
    });

    document.getElementById('orderForm').addEventListener('submit', async function (event) {
        event.preventDefault();
        document.getElementById('orderError').classList.add('hidden');

        const items = [];
        let invalid = false;
        document.querySelectorAll('.line-row').forEach(row => {
            const partId = row.querySelector('.line-part').value;
            const quantity = parseInt(row.querySelector('.line-qty').value, 10);
            const unitPrice = row.querySelector('.line-cost').value;
            if (!partId) { invalid = true; return; }
            items.push({ part_id: parseInt(partId, 10), quantity: quantity, unit_price: unitPrice });
        });

        if (invalid || items.length === 0) {
            showError('Every line needs a part selected.');
            return;
        }

        const expected = document.getElementById('orderExpected').value;
        const payload = {
            supplier_id: parseInt(document.getElementById('orderSupplier').value, 10),
            shipping_cost: document.getElementById('orderShipping').value || '0',
            notes: document.getElementById('orderNotes').value || null,
            items: items,
        };
        if (expected) payload.expected_date = `${expected}T00:00:00`;

        const submit = document.getElementById('orderSubmit');
        submit.disabled = true;
        try {
            const response = await fetch('/api/purchase-orders', {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            if (!response.ok) {
                const body = await response.json().catch(() => null);
                showError(JRF.errorMessage(body, 'Could not create the purchase order.'));
                return;
            }
            const order = await response.json();
            window.location.href = `/purchase-orders/${order.id}`;
        } catch (error) {
            console.error(error);
            showError('Could not reach the server.');
        } finally {
            submit.disabled = false;
        }
    });
})();
