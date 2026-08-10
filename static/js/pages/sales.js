/**
 * Point of Sale page: parts grid search/add-to-cart, the cart itself
 * (quantity controls, removal), the product-details modal, the payment
 * modal, and walk-in/registered customer management.
 *
 * Previously an inline <script> block in sales.html; moved out because the
 * production CSP has no 'unsafe-inline' in script-src. Every inline
 * onclick/onchange/oninput attribute - including the ones built into the
 * cart's template-literal-generated rows - has been replaced with a CSS
 * marker class / data-* attribute plus a delegated listener.
 *
 * The server-resolved tax rate can no longer be interpolated straight into
 * this file (external scripts don't go through Jinja), so it is now handed
 * over as a small JSON data island (#sales-config, written by sales.html)
 * instead - the same technique base_new.html already uses for the
 * notification bell. The value itself is unchanged: still computed
 * server-side by _tax_rate_percent(), still the single source of truth.
 */
(function () {
    'use strict';

    // Cart state
    let cart = [];
    let selectedPaymentMethod = null;
    let taxRate = 0.12; // Default tax rate, will be updated from settings
    let selectedCustomerId = null;
    let allCustomers = [];

    // DOM Elements (will be initialized after DOM loads)
    let cartItemsEl, subtotalEl, taxEl, totalEl, checkoutBtn, clearCartBtn, searchInput, processPaymentBtn, customerSelect, customerDetails, customerName, customerEmail, customerPhone, editCustomerBtn;

    function salesConfig() {
        const el = document.getElementById('sales-config');
        if (!el) return { tax_rate: 0 };
        try {
            return JSON.parse(el.textContent);
        } catch (error) {
            console.error('Could not parse sales config:', error);
            return { tax_rate: 0 };
        }
    }

    // Tax rate as a percentage, resolved server-side from settings. The view
    // already normalises the stored value (which may be 0.12 or 12), so this
    // is the single source of truth - an extra client fetch that divided the
    // stored 0.12 by 100 again made tax come out 100x too low.
    const TAX_PERCENT = Number(salesConfig().tax_rate) || 0;

    function applyTaxRate() {
        taxRate = TAX_PERCENT / 100;
        const taxLabel = document.getElementById('taxLabel');
        if (taxLabel) {
            taxLabel.textContent = `Tax (${TAX_PERCENT}%)`;
        }
        updateCart();
    }

    // Initialize the page
    document.addEventListener('DOMContentLoaded', function() {
        // Initialize DOM elements
        cartItemsEl = document.getElementById('cartItems');
        subtotalEl = document.getElementById('subtotal');
        taxEl = document.getElementById('tax');
        totalEl = document.getElementById('total');
        checkoutBtn = document.getElementById('checkoutBtn');
        clearCartBtn = document.getElementById('clearCartBtn');
        searchInput = document.getElementById('searchParts');
        processPaymentBtn = document.getElementById('processPaymentBtn');
        customerSelect = document.getElementById('customerSelect');
        customerDetails = document.getElementById('customerDetails');
        customerName = document.getElementById('customerName');
        customerEmail = document.getElementById('customerEmail');
        customerPhone = document.getElementById('customerPhone');
        editCustomerBtn = document.getElementById('editCustomerBtn');

        // Fetch tax rate from settings first
        applyTaxRate();

        // Load customers
        loadCustomers();

        // Load cart from localStorage if available
        const savedCart = localStorage.getItem('posCart');
        if (savedCart) {
            cart = JSON.parse(savedCart);
            updateCart();
        }

        // Add event listeners
        if (searchInput) {
            searchInput.addEventListener('input', searchParts);
        }

        // Cart button event listeners
        if (checkoutBtn) {
            checkoutBtn.addEventListener('click', openPaymentModal);
        }
        if (clearCartBtn) {
            clearCartBtn.addEventListener('click', clearCart);
        }
        if (customerSelect) {
            customerSelect.addEventListener('change', handleCustomerSelection);
        }
        if (editCustomerBtn) {
            editCustomerBtn.addEventListener('click', editSelectedCustomer);
        }
        if (processPaymentBtn) {
            processPaymentBtn.addEventListener('click', processPayment);
        }

        // Add event delegation for add to cart buttons and product cards
        const partsGrid = document.getElementById('partsGrid');
        if (partsGrid) {
            partsGrid.addEventListener('click', function(e) {
                // Handle add to cart button clicks - check if clicked element or its parent is a button
                const addToCartBtn = e.target.closest('.add-to-cart-btn');
                if (addToCartBtn) {
                    e.preventDefault();
                    e.stopPropagation();
                    const partId = parseInt(addToCartBtn.getAttribute('data-part-id'));
                    const partName = addToCartBtn.getAttribute('data-part-name');
                    const price = parseFloat(addToCartBtn.getAttribute('data-part-price'));
                    const stock = parseInt(addToCartBtn.getAttribute('data-part-stock'));
                    addToCart(partId, partName, price, stock);
                    return; // Exit early to prevent card click
                }
                // Handle product card clicks - only if not clicking on action buttons
                if (e.target.closest('.part-card') && !e.target.closest('button')) {
                    const card = e.target.closest('.part-card');
                    const partId = parseInt(card.getAttribute('data-id'));
                    showProductDetails(partId);
                }
            });
        }

        // Add event listener for amount received input
        const amountReceivedInput = document.getElementById('amountReceived');
        if (amountReceivedInput) {
            amountReceivedInput.addEventListener('input', calculateChange);
        }

        // Delegated handlers for what used to be inline onclick attributes:
        // the customer panel, the product-details modal, and the payment
        // modal's backdrop/close button/method buttons.
        document.addEventListener('click', function (e) {
            if (e.target.closest('.js-add-new-customer')) {
                addNewCustomer();
                return;
            }
            if (e.target.closest('.js-close-product-modal')) {
                closeProductModal();
                return;
            }
            if (e.target.closest('.js-add-to-cart-from-modal')) {
                addToCartFromModal();
                return;
            }
            if (e.target.closest('.js-close-payment-modal')) {
                closePaymentModal();
                return;
            }
            const paymentMethodBtn = e.target.closest('.js-select-payment-method');
            if (paymentMethodBtn) {
                selectPaymentMethod(paymentMethodBtn.dataset.method);
            }
        });

        // Delegated handlers for the cart rows rendered by updateCart()
        // below (dynamic markup rebuilt on every change, so the listeners
        // live on the static #cartItems container instead of each button).
        if (cartItemsEl) {
            cartItemsEl.addEventListener('click', function (e) {
                const decreaseBtn = e.target.closest('.js-qty-decrease');
                if (decreaseBtn) {
                    const id = Number(decreaseBtn.dataset.id);
                    const item = cart.find(function (i) { return i.id === id; });
                    if (item) updateQuantity(id, item.quantity - 1);
                    return;
                }
                const increaseBtn = e.target.closest('.js-qty-increase');
                if (increaseBtn) {
                    const id = Number(increaseBtn.dataset.id);
                    const item = cart.find(function (i) { return i.id === id; });
                    if (item) updateQuantity(id, item.quantity + 1);
                    return;
                }
                const removeBtn = e.target.closest('.js-remove-item');
                if (removeBtn) {
                    removeFromCart(Number(removeBtn.dataset.id));
                }
            });

            cartItemsEl.addEventListener('change', function (e) {
                const qtyInput = e.target.closest('.js-qty-input');
                if (qtyInput) {
                    updateQuantity(Number(qtyInput.dataset.id), qtyInput.value);
                }
            });
        }
    });

    // Search parts
    function searchParts() {
        const searchTerm = searchInput.value.toLowerCase();
        const partCards = document.querySelectorAll('.part-card');

        partCards.forEach(card => {
            const name = card.getAttribute('data-name').toLowerCase();
            const brand = card.getAttribute('data-brand').toLowerCase();
            const type = card.getAttribute('data-type').toLowerCase();

            if (name.includes(searchTerm) || brand.includes(searchTerm) || type.includes(searchTerm)) {
                card.style.display = 'block';
            } else {
                card.style.display = 'none';
            }
        });
    }

    // Add item to cart
    function addToCart(partId, partName, price, stock) {
        // Convert and validate inputs
        partId = parseInt(partId);
        price = parseFloat(price);
        stock = parseInt(stock);

        if (isNaN(partId) || isNaN(price) || isNaN(stock)) {
            console.error('Invalid data:', { partId, partName, price, stock });
            JRF.notify('Could not read that product.', 'error');
            return;
        }

        // Check if already in cart
        const existingItem = cart.find(item => item.id === partId);

        if (existingItem) {
            if (existingItem.quantity < stock) {
                existingItem.quantity += 1;
            } else {
                JRF.notify('Not enough stock available.', 'warning');
                return;
            }
        } else {
            if (stock > 0) {
                cart.push({
                    id: partId,
                    name: partName,
                    price: price,
                    quantity: 1,
                    stock: stock
                });
            } else {
                JRF.notify('That item is out of stock.', 'warning');
                return;
            }
        }

        updateCart();
        saveCart();
    }

    // Update cart display
    function updateCart() {
        if (cart.length === 0) {
            cartItemsEl.innerHTML = `
                <div class="text-center text-gray-500 py-8">
                    <i class="fas fa-shopping-cart text-3xl text-gray-300 mb-2"></i>
                    <p>Your cart is empty</p>
                    <p class="text-sm">Add items to get started</p>
                </div>
            `;
            checkoutBtn.disabled = true;
            subtotalEl.textContent = '₱0.00';
            taxEl.textContent = '₱0.00';
            totalEl.textContent = '₱0.00';
            document.getElementById('cartCount').textContent = '0 items';
            return;
        }

        // Calculate totals
        let subtotal = 0;
        let html = '';

        cart.forEach(item => {
            const itemTotal = item.price * item.quantity;
            subtotal += itemTotal;

            html += `
                <div class="cart-item">
                    <div class="flex items-center justify-between py-2 border-b border-gray-100">
                        <div>
                            <h4 class="text-sm font-medium text-gray-900">${escapeHtml(item.name)}</h4>
                            <div class="flex items-center mt-1">
                                <button class="js-qty-decrease text-gray-500 hover:text-gray-700" data-id="${item.id}">
                                    <i class="fas fa-minus text-xs"></i>
                                </button>
                                <input type="number"
                                       min="1"
                                       max="${item.stock}"
                                       value="${item.quantity}"
                                       class="js-qty-input w-12 mx-2 text-center border rounded py-1 text-sm"
                                       data-id="${item.id}">
                                <button class="js-qty-increase text-gray-500 hover:text-gray-700" data-id="${item.id}">
                                    <i class="fas fa-plus text-xs"></i>
                                </button>
                                <span class="text-sm text-gray-500 ml-2">× ₱${item.price.toFixed(2)}</span>
                            </div>
                        </div>
                        <div class="text-right">
                            <div class="text-sm font-medium">₱${itemTotal.toFixed(2)}</div>
                            <button class="js-remove-item text-red-500 hover:text-red-700 text-xs mt-1" data-id="${item.id}">
                                <i class="fas fa-trash"></i> Remove
                            </button>
                        </div>
                    </div>
                </div>
            `;
        });

        const tax = subtotal * taxRate; // Use dynamic tax rate from settings
        const total = subtotal + tax;

        cartItemsEl.innerHTML = html;
        subtotalEl.textContent = `₱${subtotal.toFixed(2)}`;
        taxEl.textContent = `₱${tax.toFixed(2)}`;
        totalEl.textContent = `₱${total.toFixed(2)}`;
        checkoutBtn.disabled = false;
        document.getElementById('cartCount').textContent = `${cart.length} items`;

        // Update payment total
        if (document.getElementById('paymentTotal')) {
            document.getElementById('paymentTotal').textContent = `₱${total.toFixed(2)}`;
        }
    }

    // Update item quantity
    function updateQuantity(partId, newQuantity) {
        newQuantity = parseInt(newQuantity);
        const item = cart.find(item => item.id === partId);

        if (!item) return;

        if (newQuantity < 1) {
            removeFromCart(partId);
            return;
        }

        if (newQuantity > item.stock) {
            JRF.notify(`Only ${item.stock} in stock.`, 'warning');
            return;
        }

        item.quantity = newQuantity;
        updateCart();
        saveCart();
    }

    // Remove item from cart
    function removeFromCart(partId) {
        cart = cart.filter(item => item.id !== partId);
        updateCart();
        saveCart();
    }

    // Clear cart
    function clearCart() {
        if (cart.length === 0 || confirm('Are you sure you want to clear the cart?')) {
            cart = [];
            updateCart();
            saveCart();
        }
    }

    // Save cart to localStorage
    function saveCart() {
        localStorage.setItem('posCart', JSON.stringify(cart));
    }

    // Show product details modal
    function showProductDetails(partId) {
        const card = document.querySelector(`.part-card[data-id="${partId}"]`);
        if (!card) {
            console.error('Product card not found for ID:', partId);
            return;
        }

        const productData = {
            id: partId,
            name: card.getAttribute('data-name'),
            description: card.getAttribute('data-description'),
            brand: card.getAttribute('data-brand'),
            type: card.getAttribute('data-type'),
            price: parseFloat(card.getAttribute('data-price')),
            stock: parseInt(card.getAttribute('data-stock'))
        };


        // Store current product for modal add to cart
        window.currentModalProduct = productData;

        // Update basic modal content with error checking
        const elements = {
            modalProductName: document.getElementById('modalProductName'),
            modalProductBrand: document.getElementById('modalProductBrand'),
            modalProductType: document.getElementById('modalProductType'),
            modalProductPrice: document.getElementById('modalProductPrice'),
            modalProductDescription: document.getElementById('modalProductDescription'),
            modalProductStock: document.getElementById('modalProductStock'),
            modalProductId: document.getElementById('modalProductId'),
            modalProductSku: document.getElementById('modalProductSku'),
            modalProductCategory: document.getElementById('modalProductCategory')
        };

        // Update elements with error checking
        Object.entries(elements).forEach(([id, element]) => {
            if (!element) {
                console.error(`Element not found: ${id}`);
                return;
            }
        });

        if (elements.modalProductName) elements.modalProductName.textContent = productData.name || 'No name';
        if (elements.modalProductBrand) elements.modalProductBrand.textContent = productData.brand || 'No brand';
        if (elements.modalProductType) elements.modalProductType.textContent = productData.type || 'No type';
        if (elements.modalProductPrice) elements.modalProductPrice.textContent = `₱${(productData.price || 0).toFixed(2)}`;
        if (elements.modalProductDescription) elements.modalProductDescription.textContent = productData.description || 'No description available';
        if (elements.modalProductStock) elements.modalProductStock.textContent = productData.stock || 0;
        if (elements.modalProductId) elements.modalProductId.textContent = productData.id || 'N/A';
        if (elements.modalProductSku) elements.modalProductSku.textContent = productData.id || 'N/A';
        if (elements.modalProductCategory) elements.modalProductCategory.textContent = productData.type || 'No category';

        // Update stock badge and status
        const stockBadge = document.getElementById('modalStockBadge');
        const stockStatus = document.getElementById('modalStockStatus');
        if (stockBadge && stockStatus) {
            if (productData.stock > 10) {
                stockBadge.className = 'px-4 py-2 rounded-full text-sm font-semibold bg-green-100 text-green-800';
                stockBadge.textContent = `${productData.stock} in stock`;
                stockStatus.textContent = 'Good availability';
            } else if (productData.stock > 0) {
                stockBadge.className = 'px-4 py-2 rounded-full text-sm font-semibold bg-yellow-100 text-yellow-800';
                stockBadge.textContent = `${productData.stock} left`;
                stockStatus.textContent = 'Low stock - reorder soon';
            } else {
                stockBadge.className = 'px-4 py-2 rounded-full text-sm font-semibold bg-red-100 text-red-800';
                stockBadge.textContent = 'Out of stock';
                stockStatus.textContent = 'Currently unavailable';
            }
        } else {
            console.error('Stock badge or status element not found');
        }

        // Load supplier information
        loadSupplierInfo(partId);

        // Load sales performance data
        loadSalesPerformance(partId);

        // Store current product for cart addition
        window.currentModalProduct = productData;

        // Set placeholder image
        document.getElementById('modalProductImage').src = `https://picsum.photos/seed/motorcycle-part-${partId}/600/300.jpg`;
        document.getElementById('modalProductImage').alt = productData.name;

        // Show modal
        document.getElementById('productModal').classList.remove('hidden');
    }

    // Load supplier information for a product
    function loadSupplierInfo(partId) {
        const supplierInfo = document.getElementById('modalSupplierInfo');

        // Try to get supplier data from the card or fetch from API
        const card = document.querySelector(`.part-card[data-id="${partId}"]`);
        const supplierData = card.getAttribute('data-suppliers');

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

    // Load sales performance data for a product
    async function loadSalesPerformance(partId) {
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
            // A never-sold part is normal; show zeroes rather than an error.
            setMetrics(0, 0, 0);
            return;
        }

        const data = result.data || {};
        setMetrics(data.total_sold ?? 0, data.total_revenue ?? 0, data.avg_price ?? 0);
    }

    // Add product to cart from modal
    function addToCartFromModal() {
        if (window.currentModalProduct) {
            addToCart(
                window.currentModalProduct.id,
                window.currentModalProduct.name,
                window.currentModalProduct.price,
                window.currentModalProduct.stock
            );
            closeProductModal();
        }
    }

    // Close product modal
    function closeProductModal() {
        document.getElementById('productModal').classList.add('hidden');
    }

    // Open payment modal
    function openPaymentModal() {
        if (cart.length === 0) return;

        // Update payment total
        const total = parseFloat(totalEl.textContent.replace('₱', ''));
        document.getElementById('paymentTotal').textContent = `₱${total.toFixed(2)}`;

        // Reset payment method
        selectPaymentMethod(null);

        // Show modal
        document.getElementById('paymentModal').classList.remove('hidden');
    }

    // Close payment modal
    function closePaymentModal() {
        document.getElementById('paymentModal').classList.add('hidden');
    }

    // Select payment method
    function selectPaymentMethod(method) {
        selectedPaymentMethod = method;

        // Update UI
        document.querySelectorAll('.payment-method').forEach(btn => {
            btn.classList.toggle('active', btn.getAttribute('data-method') === method);
        });

        // Show/hide payment method forms
        document.getElementById('cashPayment').classList.toggle('hidden', method !== 'cash');

        // Enable/disable process payment button
        if (processPaymentBtn) {
            processPaymentBtn.disabled = !method;
        }
    }

    // Calculate change for cash payment
    function calculateChange() {
        const amountReceived = parseFloat(document.getElementById('amountReceived').value) || 0;
        const total = parseFloat(totalEl.textContent.replace('₱', ''));
        const change = amountReceived - total;

        document.getElementById('changeAmount').textContent = `₱${change >= 0 ? change.toFixed(2) : '0.00'}`;
    }

    // Process payment
    function processPayment() {
        if (!selectedPaymentMethod) {
            JRF.notify('Select a payment method first.', 'warning');
            return;
        }

        if (selectedPaymentMethod === 'cash') {
            const amountReceived = parseFloat(document.getElementById('amountReceived').value) || 0;
            const total = parseFloat(totalEl.textContent.replace('₱', ''));
            if (amountReceived < total) {
                JRF.notify('Amount received is less than the total.', 'warning');
                return;
            }
        }

        if (cart.length === 0) {
            JRF.notify('The cart is empty.', 'warning');
            return;
        }

        // The API wants {payment_method, details:[{part_id, quantity, ...}]}
        // and computes every total itself. The previous payload sent a cart
        // envelope with client-side totals, which the schema rejected
        // outright - checkout could never record a sale.
        const payload = {
            payment_method: selectedPaymentMethod,
            details: cart.map(function (item) {
                return {
                    part_id: item.id,
                    quantity: item.quantity,
                    unit_price: String(item.price),
                    tax_percent: String(TAX_PERCENT),
                };
            }),
        };
        if (selectedCustomerId) payload.customer_id = parseInt(selectedCustomerId, 10);

        const button = document.getElementById('processPaymentBtn');
        if (button) button.disabled = true;

        JRF.api('/api/sales', { method: 'POST', body: payload }).then(function (result) {
            if (button) button.disabled = false;

            if (!result.ok) {
                JRF.notifyError(result, 'Failed to record the sale.');
                return;
            }

            const sale = result.data || {};
            JRF.notify(
                `Sale ${sale.receipt_number || ''} recorded - ${JRF.currency(sale.total_amount)}`,
                'success'
            );
            clearCart();
            closePaymentModal();
            // Stock levels and the recent-sales list are both stale now.
            setTimeout(function () { window.location.reload(); }, 1200);
        });
    }

    // Customer Management Functions
    async function loadCustomers() {
        const result = await JRF.api('/api/customers?per_page=100');
        if (!result.ok) {
            JRF.notifyError(result, 'Could not load customers.');
            return;
        }
        // The endpoint returns {customers: [...], pagination: {...}} - assigning
        // the envelope left the dropdown permanently empty.
        allCustomers = (result.data && result.data.customers) || [];
        updateCustomerDropdown();
    }

    function updateCustomerDropdown() {
        if (!customerSelect) return;

        customerSelect.innerHTML = '<option value="">Walk-in Customer</option>';
        allCustomers.forEach(customer => {
            const option = document.createElement('option');
            option.value = customer.id;
            option.textContent = `${customer.name} - ${customer.email}`;
            customerSelect.appendChild(option);
        });
    }

    function handleCustomerSelection() {
        const customerId = customerSelect.value;
        selectedCustomerId = customerId || null;

        if (customerId && editCustomerBtn) {
            editCustomerBtn.disabled = false;
        } else if (editCustomerBtn) {
            editCustomerBtn.disabled = true;
        }

        if (customerId) {
            const customer = allCustomers.find(c => c.id == customerId);
            if (customer) {
                showCustomerDetails(customer);
            }
        } else {
            hideCustomerDetails();
        }
    }

    function showCustomerDetails(customer) {
        if (!customerDetails || !customerName || !customerEmail || !customerPhone) return;

        customerName.textContent = customer.name;
        customerEmail.textContent = customer.email;
        customerPhone.textContent = customer.phone || 'No phone';
        customerDetails.classList.remove('hidden');
    }

    function hideCustomerDetails() {
        if (customerDetails) {
            customerDetails.classList.add('hidden');
        }
    }

    async function addNewCustomer() {
        const name = prompt('Enter customer name:');
        if (!name) return;

        // Email is optional on the server; only send it when given so a blank
        // prompt does not fail validation.
        const email = prompt('Enter customer email (optional):');
        const phone = prompt('Enter customer phone (optional):');
        const address = prompt('Enter customer address (optional):');

        const result = await JRF.api('/api/customers', {
            method: 'POST',
            body: {
                name: name,
                email: email || null,
                phone: phone || null,
                address: address || null,
            },
        });

        if (!result.ok) {
            JRF.notifyError(result, 'Failed to add the customer.');
            return;
        }

        // The endpoint returns the customer itself, not {customer: {...}}.
        const customer = result.data || {};
        JRF.notify(`Customer "${customer.name}" added.`, 'success');

        await loadCustomers();
        selectedCustomerId = customer.id;
        if (customerSelect) customerSelect.value = customer.id;
        handleCustomerSelection();
    }

    async function editSelectedCustomer() {
        if (!selectedCustomerId) return;

        const customer = allCustomers.find(c => c.id == selectedCustomerId);
        if (!customer) return;

        const name = prompt('Enter customer name:', customer.name);
        if (!name) return;

        // Blank clears the field rather than aborting the edit.
        const email = prompt('Enter customer email:', customer.email || '');
        const phone = prompt('Enter customer phone:', customer.phone || '');
        const address = prompt('Enter customer address:', customer.address || '');

        const result = await JRF.api(`/api/customers/${selectedCustomerId}`, {
            method: 'PUT',
            body: {
                name: name,
                email: email || null,
                phone: phone || null,
                address: address || null,
            },
        });

        if (!result.ok) {
            JRF.notifyError(result, 'Failed to update the customer.');
            return;
        }

        JRF.notify('Customer updated.', 'success');
        await loadCustomers();
        handleCustomerSelection();
    }
})();
