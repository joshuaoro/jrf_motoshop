/**
 * Suppliers page: add/edit/delete supplier modals + card search.
 * Previously an inline <script> block; moved out because the production CSP
 * has no 'unsafe-inline' in script-src. Inline onclick="..." handlers were
 * replaced with delegated click listeners keyed off marker classes
 * (.js-add-supplier, .js-close-supplier-modal, .js-close-delete-modal,
 * .js-confirm-delete) and the existing .edit-btn / .delete-btn classes.
 *
 * Bug fix while converting: `dataAttr` was declared with `const` inside the
 * `try` block but read again inside the `catch` block below it. Block
 * scoping means that reference was out of scope, so a malformed
 * data-suppliers attribute would throw "dataAttr is not defined" instead of
 * logging the actual parse error. Hoisted the declaration above the try.
 */
let suppliersData = [];
let currentSupplierId = null;

// Load suppliers data from data attribute
document.addEventListener('DOMContentLoaded', function() {
    const suppliersGrid = document.getElementById('suppliersGrid');
    if (suppliersGrid) {
        let dataAttr = null;
        try {
            dataAttr = suppliersGrid.getAttribute('data-suppliers');
            if (dataAttr) {
                // Clean the data before parsing (remove any HTML entities)
                const cleanData = dataAttr.replace(/&quot;/g, '"').replace(/&#39;/g, "'");
                suppliersData = JSON.parse(cleanData);
                console.log('Loaded suppliers data:', suppliersData.length, 'items');
                // Ensure all suppliers have id field
                suppliersData = suppliersData.map(s => ({
                    ...s,
                    id: s.id || parseInt(s.id)
                }));
                console.log('Normalized suppliers data sample:', suppliersData.slice(0, 2));
            } else {
                console.warn('No data-suppliers attribute found, will use card data as fallback');
                suppliersData = [];
            }
        } catch (error) {
            console.error('Error parsing suppliers data:', error, 'Raw data:', dataAttr);
            suppliersData = [];
        }
    } else {
        console.error('suppliersGrid element not found');
    }
});

// Search functionality
document.addEventListener('DOMContentLoaded', function () {
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.addEventListener('input', function() {
            const searchTerm = this.value.toLowerCase();
            const cards = document.querySelectorAll('.supplier-card');

            cards.forEach(card => {
                const name = card.getAttribute('data-name');
                card.style.display = name.includes(searchTerm) ? 'block' : 'none';
            });
        });
    }
});

// Modal functions
function openAddSupplierModal() {
    document.getElementById('modalTitle').textContent = 'Add Supplier';
    document.getElementById('supplierForm').reset();
    document.getElementById('supplierId').value = '';
    document.getElementById('supplierModal').classList.remove('hidden');
}

function editSupplier(button) {
    try {
        console.log('editSupplier called, button:', button);
        const supplierId = parseInt(button.getAttribute('data-supplier-id'));
        console.log('supplierId:', supplierId, 'type:', typeof supplierId);
        console.log('suppliersData length:', suppliersData.length);
        console.log('suppliersData sample:', suppliersData.slice(0, 2));

        // Try to find supplier in suppliersData array
        let supplier = suppliersData.find(s => {
            const sId = s.id;
            const sIdNum = typeof sId === 'string' ? parseInt(sId) : sId;
            const supplierIdNum = typeof supplierId === 'string' ? parseInt(supplierId) : supplierId;
            return sIdNum == supplierIdNum || sId == supplierId;
        });

        // If not found in suppliersData, try to get from the card directly
        if (!supplier) {
            console.log('Supplier not found in suppliersData, trying to get from card...');
            const card = button.closest('.supplier-card');
            if (card) {
                supplier = {
                    id: parseInt(card.getAttribute('data-id')),
                    name: card.getAttribute('data-supplier-name') || '',
                    contact_no: card.getAttribute('data-supplier-contact') || '',
                    address: card.getAttribute('data-supplier-address') || ''
                };
                console.log('Found supplier from card:', supplier);
            }
        }

        if (!supplier) {
            console.error('Supplier not found with id:', supplierId);
            console.error('Available supplier IDs in suppliersData:', suppliersData.map(s => s.id));
            alert('Error: Supplier not found. Please refresh the page.');
            return;
        }

        console.log('Found supplier:', supplier);

        const modal = document.getElementById('supplierModal');
        if (!modal) {
            console.error('supplierModal not found');
            alert('Error: Modal not found. Please refresh the page.');
            return;
        }

        document.getElementById('modalTitle').textContent = 'Edit Supplier';
        document.getElementById('supplierId').value = supplier.id;
        document.getElementById('supplierName').value = supplier.name || '';
        document.getElementById('supplierContact').value = supplier.contact_no || '';
        document.getElementById('supplierAddress').value = supplier.address || '';
        modal.classList.remove('hidden');
    } catch (error) {
        console.error('Error editing supplier:', error);
        alert('Error opening edit form. Please refresh the page.');
    }
}

function closeSupplierModal() {
    document.getElementById('supplierModal').classList.add('hidden');
}

function deleteSupplier(button) {
    const supplierId = parseInt(button.getAttribute('data-supplier-id'));
    currentSupplierId = supplierId;
    document.getElementById('deleteModal').classList.remove('hidden');
}

function closeDeleteModal() {
    document.getElementById('deleteModal').classList.add('hidden');
    currentSupplierId = null;
}

function confirmDelete() {
    if (!currentSupplierId) return;

    // Make actual API call to delete supplier
    fetch(`/api/suppliers/${currentSupplierId}`, {
        method: 'DELETE',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            closeDeleteModal();
            location.reload();
        } else {
            alert('Error: ' + data.message);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Error deleting supplier');
    });
}

// Form submission
document.addEventListener('DOMContentLoaded', function () {
    const supplierForm = document.getElementById('supplierForm');
    if (supplierForm) {
        supplierForm.addEventListener('submit', function(e) {
            e.preventDefault();

            const supplierId = document.getElementById('supplierId').value;
            const formData = {
                name: document.getElementById('supplierName').value,
                contact_no: document.getElementById('supplierContact').value,
                address: document.getElementById('supplierAddress').value
            };

            const method = supplierId ? 'PUT' : 'POST';
            const url = supplierId ? `/api/suppliers/${supplierId}` : '/api/suppliers';

            // Make actual API call
            fetch(url, {
                method: method,
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(formData)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    closeSupplierModal();
                    location.reload();
                } else {
                    alert('Error: ' + data.message);
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Error saving supplier');
            });
        });
    }
});

// Delegated click handling for buttons that used to carry inline onclick=""
document.addEventListener('click', function (e) {
    if (e.target.closest('.js-add-supplier')) {
        openAddSupplierModal();
        return;
    }
    if (e.target.closest('.js-close-supplier-modal')) {
        closeSupplierModal();
        return;
    }
    if (e.target.closest('.js-close-delete-modal')) {
        closeDeleteModal();
        return;
    }
    if (e.target.closest('.js-confirm-delete')) {
        confirmDelete();
        return;
    }

    const editBtn = e.target.closest('.edit-btn');
    if (editBtn) {
        editSupplier(editBtn);
        return;
    }

    const deleteBtn = e.target.closest('.delete-btn');
    if (deleteBtn) {
        deleteSupplier(deleteBtn);
    }
});
