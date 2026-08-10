/**
 * Expenses page: record/edit/delete expense modal and delete confirmation.
 * Previously an inline <script> block plus onclick= attributes; moved out
 * and switched to event delegation because the production CSP has no
 * 'unsafe-inline' in script-src.
 */
(function () {
    'use strict';

    let deleteTargetId = null;

    function showError(message) {
        const box = document.getElementById('expenseError');
        box.textContent = message;
        box.classList.remove('hidden');
    }

    function clearError() {
        document.getElementById('expenseError').classList.add('hidden');
    }

    function openExpenseModal() {
        clearError();
        document.getElementById('expenseModalTitle').textContent = 'Record Expense';
        document.getElementById('expenseForm').reset();
        document.getElementById('expenseId').value = '';
        document.getElementById('expenseModal').classList.remove('hidden');
    }

    function editExpense(button) {
        clearError();
        const expense = JSON.parse(button.getAttribute('data-expense'));

        document.getElementById('expenseModalTitle').textContent = 'Edit Expense';
        document.getElementById('expenseId').value = expense.id;
        document.getElementById('expenseCategory').value = expense.category;
        document.getElementById('expenseAmount').value = expense.amount;
        document.getElementById('expenseDescription').value = expense.description || '';
        document.getElementById('expensePaymentMethod').value = expense.payment_method;
        document.getElementById('expenseDate').value =
            expense.expense_date ? expense.expense_date.slice(0, 10) : '';
        document.getElementById('expenseVendor').value = expense.vendor || '';
        document.getElementById('expenseReceipt').value = expense.receipt_number || '';
        document.getElementById('expenseNotes').value = expense.notes || '';
        document.getElementById('expenseModal').classList.remove('hidden');
    }

    function closeExpenseModal() {
        document.getElementById('expenseModal').classList.add('hidden');
    }

    function askDelete(button) {
        deleteTargetId = button.getAttribute('data-expense-id');
        document.getElementById('deleteModal').classList.remove('hidden');
    }

    function closeDeleteModal() {
        document.getElementById('deleteModal').classList.add('hidden');
        deleteTargetId = null;
    }

    async function confirmDelete() {
        if (!deleteTargetId) return;
        try {
            const response = await fetch(`/api/expenses/${deleteTargetId}`, {
                method: 'DELETE',
                credentials: 'same-origin',
            });
            if (!response.ok) {
                const payload = await response.json().catch(() => null);
                alert(JRF.errorMessage(payload, 'Could not delete the expense.'));
                return;
            }
            location.reload();
        } catch (error) {
            console.error(error);
            alert('Could not reach the server.');
        }
    }

    document.addEventListener('click', function (event) {
        if (event.target.closest('.js-open-expense-modal')) {
            openExpenseModal();
            return;
        }
        if (event.target.closest('.js-close-expense-modal')) {
            closeExpenseModal();
            return;
        }
        const editButton = event.target.closest('.js-edit-expense');
        if (editButton) {
            editExpense(editButton);
            return;
        }
        const deleteButton = event.target.closest('.js-ask-delete-expense');
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

    document.getElementById('expenseForm').addEventListener('submit', async function (event) {
        event.preventDefault();
        clearError();

        const submit = document.getElementById('expenseSubmit');
        const expenseId = document.getElementById('expenseId').value;
        const dateValue = document.getElementById('expenseDate').value;

        const payload = {
            category: document.getElementById('expenseCategory').value,
            amount: document.getElementById('expenseAmount').value,
            description: document.getElementById('expenseDescription').value,
            payment_method: document.getElementById('expensePaymentMethod').value,
            vendor: document.getElementById('expenseVendor').value || null,
            receipt_number: document.getElementById('expenseReceipt').value || null,
            notes: document.getElementById('expenseNotes').value || null,
        };
        // A bare date needs a time component to parse as a datetime.
        if (dateValue) payload.expense_date = `${dateValue}T00:00:00`;

        submit.disabled = true;
        try {
            const response = await fetch(
                expenseId ? `/api/expenses/${expenseId}` : '/api/expenses',
                {
                    method: expenseId ? 'PUT' : 'POST',
                    credentials: 'same-origin',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                }
            );

            // Success is the 2xx status, not a `success` field - these
            // endpoints return the saved object.
            if (!response.ok) {
                const body = await response.json().catch(() => null);
                showError(JRF.errorMessage(body, 'Could not save the expense.'));
                return;
            }
            location.reload();
        } catch (error) {
            console.error(error);
            showError('Could not reach the server.');
        } finally {
            submit.disabled = false;
        }
    });
})();
