/**
 * Staff page: add/edit/delete staff modals + card search/role filter.
 * Previously an inline <script> block; moved out because the production CSP
 * has no 'unsafe-inline' in script-src. Inline onclick="..." handlers were
 * replaced with delegated click listeners keyed off marker classes
 * (.js-add-staff, .js-close-staff-modal, .js-close-delete-modal,
 * .js-confirm-delete) and the existing .edit-btn / .delete-btn classes.
 *
 * Bug fix while converting: `dataAttr` was declared with `const` inside the
 * `try` block but read again inside the `catch` block below it. Block
 * scoping means that reference was out of scope, so a malformed
 * data-staff attribute would throw "dataAttr is not defined" instead of
 * logging the actual parse error. Hoisted the declaration above the try.
 */
let staffData = [];
let currentStaffId = null;

// Load staff data from data attribute
document.addEventListener('DOMContentLoaded', function() {
    const staffGrid = document.getElementById('staffGrid');
    if (staffGrid) {
        let dataAttr = null;
        try {
            dataAttr = staffGrid.getAttribute('data-staff');
            if (dataAttr) {
                // Clean the data before parsing (remove any HTML entities)
                const cleanData = dataAttr.replace(/&quot;/g, '"').replace(/&#39;/g, "'");
                staffData = JSON.parse(cleanData);
                console.log('Loaded staff data:', staffData.length, 'items');
                // Ensure all staff have id field
                staffData = staffData.map(s => ({
                    ...s,
                    id: s.id || parseInt(s.id)
                }));
                console.log('Normalized staff data sample:', staffData.slice(0, 2));
            } else {
                console.warn('No data-staff attribute found, will use card data as fallback');
                staffData = [];
            }
        } catch (error) {
            console.error('Error parsing staff data:', error, 'Raw data:', dataAttr);
            staffData = [];
        }
    } else {
        console.error('staffGrid element not found');
    }
});

// Search and filter functionality
document.addEventListener('DOMContentLoaded', function () {
    const searchInput = document.getElementById('searchInput');
    const roleFilter = document.getElementById('roleFilter');
    if (searchInput) searchInput.addEventListener('input', filterStaff);
    if (roleFilter) roleFilter.addEventListener('change', filterStaff);
});

function filterStaff() {
    const searchTerm = document.getElementById('searchInput').value.toLowerCase();
    const roleFilter = document.getElementById('roleFilter').value;
    const cards = document.querySelectorAll('.staff-card');

    cards.forEach(card => {
        const name = card.getAttribute('data-name');
        const role = card.getAttribute('data-role');
        const matchesSearch = name.includes(searchTerm);
        const matchesRole = !roleFilter || role === roleFilter;

        card.style.display = matchesSearch && matchesRole ? 'block' : 'none';
    });
}

// Modal functions
function openAddStaffModal() {
    document.getElementById('modalTitle').textContent = 'Add Staff Member';
    document.getElementById('staffForm').reset();
    document.getElementById('staffId').value = '';
    document.getElementById('staffModal').classList.remove('hidden');
}

function editStaff(button) {
    try {
        console.log('editStaff called, button:', button);
        const staffId = parseInt(button.getAttribute('data-staff-id'));
        console.log('staffId:', staffId, 'type:', typeof staffId);
        console.log('staffData length:', staffData.length);
        console.log('staffData sample:', staffData.slice(0, 2));

        // Try to find staff in staffData array
        let staff = staffData.find(s => {
            const sId = s.id;
            const sIdNum = typeof sId === 'string' ? parseInt(sId) : sId;
            const staffIdNum = typeof staffId === 'string' ? parseInt(staffId) : staffId;
            return sIdNum == staffIdNum || sId == staffId;
        });

        // If not found in staffData, try to get from the card directly
        if (!staff) {
            console.log('Staff not found in staffData, trying to get from card...');
            const card = button.closest('.staff-card');
            if (card) {
                staff = {
                    id: parseInt(card.getAttribute('data-id')),
                    name: card.getAttribute('data-staff-name') || '',
                    email: card.getAttribute('data-staff-email') || '',
                    username: card.getAttribute('data-staff-username') || '',
                    role: card.getAttribute('data-staff-role') || '',
                    contact_no: card.getAttribute('data-staff-contact') || ''
                };
                console.log('Found staff from card:', staff);
            }
        }

        if (!staff) {
            console.error('Staff not found with id:', staffId);
            console.error('Available staff IDs in staffData:', staffData.map(s => s.id));
            alert('Error: Staff member not found. Please refresh the page.');
            return;
        }

        console.log('Found staff:', staff);

        const modal = document.getElementById('staffModal');
        if (!modal) {
            console.error('staffModal not found');
            alert('Error: Modal not found. Please refresh the page.');
            return;
        }

        document.getElementById('modalTitle').textContent = 'Edit Staff Member';
        document.getElementById('staffId').value = staff.id;
        document.getElementById('staffName').value = staff.name || '';
        document.getElementById('staffEmail').value = staff.email || '';
        document.getElementById('staffUsername').value = staff.username || '';
        document.getElementById('staffRole').value = staff.role || '';
        document.getElementById('staffContact').value = staff.contact_no || '';
        document.getElementById('staffPassword').value = ''; // Don't populate password
        modal.classList.remove('hidden');
    } catch (error) {
        console.error('Error editing staff:', error);
        alert('Error opening edit form. Please refresh the page.');
    }
}

function closeStaffModal() {
    document.getElementById('staffModal').classList.add('hidden');
}

function deleteStaff(button) {
    const staffId = parseInt(button.getAttribute('data-staff-id'));
    currentStaffId = staffId;
    document.getElementById('deleteModal').classList.remove('hidden');
}

function closeDeleteModal() {
    document.getElementById('deleteModal').classList.add('hidden');
    currentStaffId = null;
}

function confirmDelete() {
    if (!currentStaffId) return;

    // Make actual API call to delete staff
    fetch(`/api/staff/${currentStaffId}`, {
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
        alert('Error deleting staff member');
    });
}

// Form submission
document.addEventListener('DOMContentLoaded', function () {
    const staffForm = document.getElementById('staffForm');
    if (staffForm) {
        staffForm.addEventListener('submit', function(e) {
            e.preventDefault();

            const staffId = document.getElementById('staffId').value;
            const formData = {
                name: document.getElementById('staffName').value,
                email: document.getElementById('staffEmail').value,
                username: document.getElementById('staffUsername').value,
                role: document.getElementById('staffRole').value,
                password: document.getElementById('staffPassword').value,
                contact_no: document.getElementById('staffContact').value
            };

            const method = staffId ? 'PUT' : 'POST';
            const url = staffId ? `/api/staff/${staffId}` : '/api/staff';

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
                    closeStaffModal();
                    location.reload();
                } else {
                    alert('Error: ' + data.message);
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Error saving staff member');
            });
        });
    }
});

// Delegated click handling for buttons that used to carry inline onclick=""
document.addEventListener('click', function (e) {
    if (e.target.closest('.js-add-staff')) {
        openAddStaffModal();
        return;
    }
    if (e.target.closest('.js-close-staff-modal')) {
        closeStaffModal();
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
        editStaff(editBtn);
        return;
    }

    const deleteBtn = e.target.closest('.delete-btn');
    if (deleteBtn) {
        deleteStaff(deleteBtn);
    }
});
