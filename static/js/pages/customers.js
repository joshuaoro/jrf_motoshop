/**
 * Customers page: add/edit/delete customer modal + table search.
 * Previously an inline <script> block; moved out because the production CSP
 * has no 'unsafe-inline' in script-src. Inline onclick="closeCustomerModal()"
 * handlers were replaced with a delegated click listener keyed off the
 * .js-close-customer-modal marker class.
 */
let currentCustomerId = null;

// Customer management functions
function openCustomerModal(customerId = null) {
    currentCustomerId = customerId;
    const modal = document.getElementById('customerModal');
    const modalTitle = document.getElementById('modalTitle');
    const form = document.getElementById('customerForm');

    if (customerId) {
        modalTitle.textContent = 'Edit Customer';
        // Load customer data
        fetch(`/api/customers/${customerId}`)
            .then(response => response.json())
            .then(customer => {
                document.getElementById('customerName').value = customer.name;
                document.getElementById('customerEmail').value = customer.email || '';
                document.getElementById('customerPhone').value = customer.phone || '';
                document.getElementById('customerAddress').value = customer.address || '';
            });
    } else {
        modalTitle.textContent = 'Add Customer';
        form.reset();
    }

    modal.classList.remove('hidden');
}

function closeCustomerModal() {
    document.getElementById('customerModal').classList.add('hidden');
    currentCustomerId = null;
}

function saveCustomer(event) {
    event.preventDefault();

    const customerData = {
        name: document.getElementById('customerName').value,
        email: document.getElementById('customerEmail').value,
        phone: document.getElementById('customerPhone').value,
        address: document.getElementById('customerAddress').value
    };

    const url = currentCustomerId ? `/api/customers/${currentCustomerId}` : '/api/customers';
    const method = currentCustomerId ? 'PUT' : 'POST';

    fetch(url, {
        method: method,
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(customerData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            closeCustomerModal();
            location.reload();
        } else {
            alert(data.message || 'Failed to save customer');
        }
    })
    .catch(error => {
        console.error('Error saving customer:', error);
        alert('Failed to save customer');
    });
}

function deleteCustomer(customerId) {
    if (confirm('Are you sure you want to delete this customer?')) {
        fetch(`/api/customers/${customerId}`, {
            method: 'DELETE'
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                location.reload();
            } else {
                alert(data.message || 'Failed to delete customer');
            }
        })
        .catch(error => {
            console.error('Error deleting customer:', error);
            alert('Failed to delete customer');
        });
    }
}

// Event listeners
document.addEventListener('DOMContentLoaded', function() {
    /**
     * Attach a listener only if the element is actually on the page.
     *
     * `addFirstCustomer` only renders in the empty state. Calling
     * addEventListener on the resulting null threw, which aborted the rest of
     * this handler - so with even one customer present, search, the form and
     * the row action buttons were all left unwired.
     */
    const on = (id, event, handler) => {
        const element = document.getElementById(id);
        if (element) element.addEventListener(event, handler);
    };

    on('addCustomerBtn', 'click', () => openCustomerModal());
    on('addFirstCustomer', 'click', () => openCustomerModal());
    on('customerForm', 'submit', saveCustomer);

    // Action buttons + modal close buttons (delegated so it also works for
    // rows/markup not present at load time)
    document.addEventListener('click', function(e) {
        if (e.target.closest('.js-close-customer-modal')) {
            closeCustomerModal();
            return;
        }

        const button = e.target.closest('button');
        if (button && button.dataset.action) {
            const customerId = button.dataset.customerId;
            if (customerId) {
                if (button.dataset.action === 'edit') {
                    openCustomerModal(customerId);
                } else if (button.dataset.action === 'delete') {
                    deleteCustomer(customerId);
                }
            }
        }
    });

    // Search functionality
    on('searchInput', 'input', function (e) {
        const searchTerm = e.target.value.toLowerCase();
        document.querySelectorAll('#customersTable tbody tr').forEach(row => {
            const text = row.textContent.toLowerCase();
            row.style.display = text.includes(searchTerm) ? '' : 'none';
        });
    });
});
