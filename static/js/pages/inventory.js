/**
 * Inventory page: parts table search/filter, product-details modal, the
 * add/edit part form, its supplier picker, and the delete-confirmation
 * modal.
 *
 * Previously an inline <script> block in inventory.html; moved out because
 * the production CSP has no 'unsafe-inline' in script-src. Every inline
 * onclick/onchange attribute (static and template-literal-built) has been
 * replaced with a CSS marker class / data-* attribute plus a delegated
 * listener, per the same pattern used by sales.js and base.js.
 *
 * Bugs fixed while converting (all pre-existing, unrelated to CSP):
 *  - searchInput/categoryFilter/partsTableBody used to be declared with
 *    `const` *inside* the DOMContentLoaded callback, but filterParts() is a
 *    top-level function that reads those same names - it could not see the
 *    callback-local bindings. The category filter's 'change' listener DID
 *    get attached (its id matched), so changing categories threw a
 *    ReferenceError instead of filtering. They are now module-level
 *    variables assigned (not redeclared) inside DOMContentLoaded, matching
 *    the working pattern in sales.js.
 *  - The search box's real id is "searchInput" (see inventory.html), but
 *    the code looked up "searchParts" (leftover from copy-pasting
 *    sales.html), so its 'input' listener was never attached and the search
 *    box did nothing at all.
 *  - currentProductId was never declared - it relied on sloppy-mode
 *    implicit global creation, which throws under 'use strict'. Declared
 *    explicitly alongside the other module state.
 */
(function () {
    'use strict';

    // Initialize variables
    let partsData = [];
    let currentPartId = null;
    let currentProductId = null;
    let selectedSupplierIds = new Set();
    let allSuppliers = [];
    let searchInput, categoryFilter, partsTableBody;

    // Load suppliers on page load
    document.addEventListener('DOMContentLoaded', function() {
        // Initialize DOM elements
        searchInput = document.getElementById('searchInput');
        categoryFilter = document.getElementById('categoryFilter');
        partsTableBody = document.getElementById('partsTableBody');
        const addPartBtn = document.getElementById('addPartBtn');
        const addFirstPart = document.getElementById('addFirstPart');

        loadSuppliers();

        if (partsTableBody) {
            try {
                const dataAttr = partsTableBody.getAttribute('data-parts');
                if (dataAttr) {
                    // Clean the data before parsing (remove any HTML entities)
                    const cleanData = dataAttr.replace(/&quot;/g, '"').replace(/&#39;/g, "'");
                    partsData = JSON.parse(cleanData);
                    // Ensure all parts have both id and part_id
                    partsData = partsData.map(p => ({
                        ...p,
                        id: p.id || p.part_id,
                        part_id: p.part_id || p.id,
                        type: p.type || p.part_type,
                        stock: p.stock || p.stock_quantity
                    }));
                } else {
                    console.warn('No data-parts attribute found, will use row data as fallback');
                    partsData = [];
                }
            } catch (error) {
                console.error('Error parsing parts data:', error);
                partsData = [];
            }
        } else {
            console.error('partsTableBody element not found');
        }

        // Add event listeners
        if (searchInput) {
            searchInput.addEventListener('input', filterParts);
        }
        if (categoryFilter) {
            categoryFilter.addEventListener('change', filterParts);
        }

        // Add event delegation for table interactions
        if (partsTableBody) {
            partsTableBody.addEventListener('click', function(e) {
                // Handle action button clicks - check if clicked element or its parent is a button
                const btn = e.target.closest('button[data-action]');
                if (btn) {
                    e.preventDefault();
                    e.stopPropagation();
                    const action = btn.getAttribute('data-action');
                    const partId = parseInt(btn.getAttribute('data-part-id'));

                    if (action === 'edit') {
                        editPart(partId);
                    } else if (action === 'reorder') {
                        reorderPart(partId);
                    } else if (action === 'delete') {
                        deletePart(partId);
                    }
                    return; // Exit early to prevent row click
                }

                // Handle row clicks for product details - only if not clicking on action buttons
                if (e.target.closest('.part-row') && !e.target.closest('button')) {
                    const row = e.target.closest('.part-row');
                    const partId = parseInt(row.getAttribute('data-id'));
                    showProductDetails(partId);
                }
            });
        }

        // Add event listeners for buttons
        if (addPartBtn) {
            addPartBtn.addEventListener('click', openAddPartModal);
        }
        if (addFirstPart) {
            addFirstPart.addEventListener('click', openAddPartModal);
        }
        const availableSuppliers = document.getElementById('availableSuppliers');
        if (availableSuppliers) {
            availableSuppliers.addEventListener('change', addSupplierToPart);
        }

        // Delegated handlers for what used to be inline onclick attributes on
        // the product-details modal, the add/edit part modal, and the delete
        // confirmation modal.
        document.addEventListener('click', function (e) {
            if (e.target.closest('.js-close-product-modal')) {
                closeProductModal();
                return;
            }
            if (e.target.closest('.js-edit-current-part')) {
                editPart(currentProductId);
                return;
            }
            if (e.target.closest('.js-close-part-modal')) {
                closePartModal();
                return;
            }
            if (e.target.closest('.js-save-part')) {
                savePart();
                return;
            }
            if (e.target.closest('.js-confirm-delete')) {
                confirmDelete();
                return;
            }
            if (e.target.closest('.js-close-delete-modal')) {
                closeDeleteModal();
                return;
            }
        });

        // Delegated handler for the "remove supplier" buttons rendered by
        // updateSelectedSuppliersDisplay() below (dynamic markup, so the
        // listener lives on the static container instead of each button).
        const selectedSuppliers = document.getElementById('selectedSuppliers');
        if (selectedSuppliers) {
            selectedSuppliers.addEventListener('click', function (e) {
                const removeBtn = e.target.closest('.js-remove-supplier');
                if (removeBtn) {
                    removeSupplierFromPart(parseInt(removeBtn.dataset.supplierId, 10));
                }
            });
        }
    });

    // Supplier management functions
    async function loadSuppliers() {
        const result = await JRF.api('/api/suppliers?per_page=100');
        if (!result.ok) {
            JRF.notifyError(result, 'Could not load suppliers.');
            return;
        }
        // The endpoint returns {suppliers: [...], pagination: {...}}. Assigning
        // the envelope straight to allSuppliers left .forEach() undefined, so
        // the dropdown silently stayed empty.
        allSuppliers = (result.data && result.data.suppliers) || [];
        updateSupplierDropdown();
    }

    function updateSupplierDropdown() {
        const select = document.getElementById('availableSuppliers');
        if (!select) return;

        select.innerHTML = '<option value="">Select a supplier to add...</option>';

        allSuppliers.forEach(supplier => {
            if (!selectedSupplierIds.has(supplier.id)) {
                const option = document.createElement('option');
                option.value = supplier.id;
                option.textContent = supplier.name;
                select.appendChild(option);
            }
        });
    }

    function addSupplierToPart() {
        const select = document.getElementById('availableSuppliers');
        const supplierId = parseInt(select.value);

        if (!supplierId) return;

        const supplier = allSuppliers.find(s => s.id === supplierId);
        if (!supplier) return;

        selectedSupplierIds.add(supplierId);
        updateSelectedSuppliersDisplay();
        updateSupplierDropdown();

        // Reset dropdown
        select.value = '';
    }

    function removeSupplierFromPart(supplierId) {
        selectedSupplierIds.delete(supplierId);
        updateSelectedSuppliersDisplay();
        updateSupplierDropdown();
    }

    function updateSelectedSuppliersDisplay() {
        const container = document.getElementById('selectedSuppliers');
        if (!container) return;

        if (selectedSupplierIds.size === 0) {
            container.innerHTML = '<span class="text-gray-400 text-sm">No suppliers selected</span>';
            return;
        }

        container.innerHTML = '';
        selectedSupplierIds.forEach(supplierId => {
            const supplier = allSuppliers.find(s => s.id === supplierId);
            if (!supplier) return;

            const badge = document.createElement('span');
            badge.className = 'inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800';
            badge.innerHTML = `
                ${escapeHtml(supplier.name)}
                <button type="button" class="js-remove-supplier ml-2 text-blue-600 hover:text-blue-800" data-supplier-id="${supplierId}">
                    <i class="fas fa-times"></i>
                </button>
            `;
            container.appendChild(badge);
        });
    }

    // Functions
    function filterParts() {
        const searchTerm = searchInput.value.toLowerCase();
        const category = categoryFilter.value;

        const rows = partsTableBody.getElementsByTagName('tr');

        for (let row of rows) {
            if (row.getAttribute('data-category') === null) continue;

            const name = row.cells[0].textContent.toLowerCase();
            const partCategory = row.getAttribute('data-category');
            const matchesSearch = name.includes(searchTerm);
            const matchesCategory = !category || partCategory === category;

            if (matchesSearch && matchesCategory) {
                row.style.display = '';
            } else {
                row.style.display = 'none';
            }
        }
    }

    // Show product details modal
    function showProductDetails(partId) {
        const row = document.querySelector(`tr[data-id="${partId}"]`);
        if (!row) return;

        currentProductId = partId;

        const productData = {
            id: partId,
            name: row.getAttribute('data-name'),
            description: row.getAttribute('data-description'),
            brand: row.getAttribute('data-brand'),
            type: row.getAttribute('data-type'),
            price: parseFloat(row.getAttribute('data-price')),
            stock: parseInt(row.getAttribute('data-stock')),
            minStock: parseInt(row.getAttribute('data-min-stock'), 10) || 5
        };

        // Update modal content
        document.getElementById('modalProductName').textContent = productData.name;
        document.getElementById('modalProductBrand').textContent = productData.brand;
        document.getElementById('modalProductType').textContent = productData.type;
        document.getElementById('modalProductPrice').textContent = `₱${productData.price.toFixed(2)}`;
        document.getElementById('modalProductDescription').textContent = productData.description;
        document.getElementById('modalProductStock').textContent = productData.stock;
        document.getElementById('modalProductId').textContent = productData.id;
        document.getElementById('modalProductSku').textContent = productData.id;
        document.getElementById('modalProductCategory').textContent = productData.type;

        // Update stock badge and status
        const stockBadge = document.getElementById('modalStockBadge');
        const stockStatus = document.getElementById('modalStockStatus');
        const reorderPoint = productData.minStock;
        if (productData.stock <= 0) {
            stockBadge.className = 'px-4 py-2 rounded-full text-sm font-semibold bg-red-100 text-red-800';
            stockBadge.textContent = 'Out of stock';
            stockStatus.textContent = 'Currently unavailable';
        } else if (productData.stock <= reorderPoint) {
            stockBadge.className = 'px-4 py-2 rounded-full text-sm font-semibold bg-yellow-100 text-yellow-800';
            stockBadge.textContent = `${productData.stock} left`;
            stockStatus.textContent = 'Low stock - reorder soon';
        } else if (productData.stock <= reorderPoint * 2) {
            stockBadge.className = 'px-4 py-2 rounded-full text-sm font-semibold bg-blue-100 text-blue-800';
            stockBadge.textContent = `${productData.stock} in stock`;
            stockStatus.textContent = 'Moderate stock';
        } else {
            stockBadge.className = 'px-4 py-2 rounded-full text-sm font-semibold bg-green-100 text-green-800';
            stockBadge.textContent = `${productData.stock} in stock`;
            stockStatus.textContent = 'Good availability';
        }

        // Load supplier information
        loadSupplierInfoForInventory(partId);

        // Load sales performance data
        loadSalesPerformanceForInventory(partId);

        // Set placeholder image
        document.getElementById('modalProductImage').src = `https://picsum.photos/seed/motorcycle-part-${partId}/600/300.jpg`;
        document.getElementById('modalProductImage').alt = productData.name;

        // Show modal
        document.getElementById('productModal').classList.remove('hidden');
    }

    // Load supplier information for inventory modal
    function loadSupplierInfoForInventory(partId) {
        const supplierInfo = document.getElementById('modalSupplierInfo');

        // Try to get supplier data from the row or fetch from API
        const row = document.querySelector(`tr[data-id="${partId}"]`);
        const supplierData = row.getAttribute('data-suppliers');

        if (supplierData && supplierData !== 'null' && supplierData !== '[]' && supplierData !== '') {
            try {
                // Clean the data before parsing (remove any HTML entities)
                const cleanData = supplierData.replace(/&quot;/g, '"').replace(/&#39;/g, "'");
                const suppliers = JSON.parse(cleanData);

                if (suppliers && Array.isArray(suppliers) && suppliers.length > 0) {
                    supplierInfo.innerHTML = suppliers.map(supplier => `
                        <div class="flex items-center justify-between bg-white rounded-lg p-2">
                            <div class="flex items-center">
                                <i class="fas fa-building text-blue-600 mr-2"></i>
                                <span class="text-sm font-medium text-blue-900">${escapeHtml(supplier.name)}</span>
                            </div>
                            <span class="text-xs text-blue-600">Primary</span>
                        </div>
                    `).join('');
                } else {
                    supplierInfo.innerHTML = '<p class="text-sm text-blue-700">No suppliers assigned</p>';
                }
            } catch (e) {
                console.error('Error parsing supplier data:', e, 'Raw data:', supplierData);
                supplierInfo.innerHTML = '<p class="text-sm text-blue-700">No suppliers assigned</p>';
            }
        } else {
            supplierInfo.innerHTML = '<p class="text-sm text-blue-700">No suppliers assigned</p>';
        }
    }

    // Load sales performance data for inventory modal
    async function loadSalesPerformanceForInventory(partId) {
        const setMetrics = (sold, revenue, avgPrice) => {
            const soldEl = document.getElementById('modalTotalSold');
            const revenueEl = document.getElementById('modalRevenue');
            const avgEl = document.getElementById('modalAvgPrice');
            if (soldEl) soldEl.textContent = sold;
            if (revenueEl) revenueEl.textContent = JRF.currency(revenue);
            if (avgEl) avgEl.textContent = JRF.currency(avgPrice);
        };

        const result = await JRF.api(`/api/parts/${partId}/sales-metrics`);
        if (!result.ok) {
            // A part with no sales is normal, not an error worth a toast.
            setMetrics(0, 0, 0);
            return;
        }

        const data = result.data || {};
        setMetrics(data.total_sold ?? 0, data.total_revenue ?? 0, data.avg_price ?? 0);
    }

    // Close product modal
    function closeProductModal() {
        document.getElementById('productModal').classList.add('hidden');
        currentProductId = null;
    }

    function openAddPartModal() {
        try {
            const modal = document.getElementById('partModal');
            if (!modal) {
                JRF.notify('Could not open the form. Please refresh the page.', 'error');
                return;
            }
            document.getElementById('modalTitle').textContent = 'Add New Part';
            document.getElementById('partForm').reset();
            document.getElementById('partId').value = '';
            currentPartId = null;

            // Clear suppliers
            selectedSupplierIds.clear();
            updateSelectedSuppliersDisplay();
            updateSupplierDropdown();

            modal.classList.remove('hidden');
        } catch (error) {
            console.error('openAddPartModal failed', error);
            JRF.notify('Could not open the form. Please refresh the page.', 'error');
        }
    }

    /** Find a part by id in the embedded data, falling back to its table row. */
    function findPart(partId) {
        const wanted = parseInt(partId, 10);

        const fromData = partsData.find(function (p) {
            return parseInt(p.part_id || p.id, 10) === wanted;
        });
        if (fromData) return fromData;

        const row = document.querySelector(`tr.part-row[data-id="${wanted}"]`);
        if (!row) return null;

        return {
            id: wanted,
            part_id: wanted,
            name: row.getAttribute('data-name'),
            brand: row.getAttribute('data-brand') || '',
            part_type: row.getAttribute('data-type') || 'engine',
            price: parseFloat(row.getAttribute('data-price')) || 0,
            cost_price: parseFloat(row.getAttribute('data-cost')) || 0,
            stock_quantity: parseInt(row.getAttribute('data-stock'), 10) || 0,
            description: row.getAttribute('data-description') || '',
        };
    }

    function editPart(partId) {
        try {
            const part = findPart(partId);
            if (!part) {
                JRF.notify('That part is no longer on this page. Refresh and try again.', 'error');
                return;
            }

            closeProductModal();

            const modal = document.getElementById('partModal');
            if (!modal) return;

            document.getElementById('modalTitle').textContent = 'Edit Part';
            document.getElementById('partId').value = part.part_id || part.id;
            document.getElementById('partName').value = part.name || '';
            document.getElementById('partBrand').value = part.brand || '';
            document.getElementById('partType').value = part.part_type || part.type || 'engine';
            document.getElementById('partPrice').value = part.price || '0.00';
            document.getElementById('partCost').value = part.cost_price ?? '0.00';
            document.getElementById('partStock').value = part.stock_quantity || part.stock || '0';
            document.getElementById('partDescription').value = part.description || '';

            // Load existing suppliers
            selectedSupplierIds.clear();
            if (part.suppliers && part.suppliers.length > 0) {
                part.suppliers.forEach(supplier => {
                    selectedSupplierIds.add(supplier.id);
                });
            }
            updateSelectedSuppliersDisplay();
            updateSupplierDropdown();

            currentPartId = partId;
            modal.classList.remove('hidden');
        } catch (error) {
            console.error('editPart failed', error);
            JRF.notify('Could not open the edit form. Please refresh the page.', 'error');
        }
    }

    function closePartModal() {
        document.getElementById('partModal').classList.add('hidden');
        currentPartId = null;
    }

    async function savePart() {
        const form = document.getElementById('partForm');
        if (!form) return;

        const formData = new FormData(form);
        const partData = {
            name: formData.get('partName'),
            brand: formData.get('partBrand'),
            part_type: formData.get('partType'),
            price: formData.get('partPrice') || '0',
            cost_price: formData.get('partCost') || '0',
            stock_quantity: parseInt(formData.get('partStock'), 10) || 0,
            description: formData.get('partDescription') || null,
            supplier_ids: Array.from(selectedSupplierIds),
        };

        if (!partData.name || !partData.brand || !partData.part_type) {
            JRF.notify('Name, brand and type are required.', 'warning');
            return;
        }

        const partId = formData.get('partId');
        const result = await JRF.api(partId ? `/api/parts/${partId}` : '/api/parts', {
            method: partId ? 'PUT' : 'POST',
            body: partData,
        });

        if (!result.ok) {
            JRF.notifyError(result, 'Failed to save the part.');
            return;
        }
        window.location.reload();
    }

    function deletePart(partId) {
        currentPartId = partId;
        JRF.openModal('deleteModal');
    }

    async function confirmDelete() {
        if (!currentPartId) return;

        const result = await JRF.api(`/api/parts/${currentPartId}`, { method: 'DELETE' });
        if (!result.ok) {
            JRF.notifyError(result, 'Failed to delete the part.');
            return;
        }
        window.location.reload();
    }

    function closeDeleteModal() {
        JRF.closeModal('deleteModal');
    }
})();
