/**
 * Reports & Analytics page: summary cards, Chart.js graphs, today's sales
 * table, top products, and low stock tables - all populated from the
 * dashboard API.
 *
 * Previously inline in reports.html - blocked outright under the production
 * CSP (no 'unsafe-inline' in script-src). The currency symbol used to be
 * baked in via Jinja (`'{{ currency_symbol }}'`); an external .js file can't
 * contain Jinja, so it's now read from the `#reports-config` JSON data
 * block the template renders (same pattern as base.js's notification data).
 */
(function () {
    'use strict';

    function config() {
        const el = document.getElementById('reports-config');
        if (!el) return { currencySymbol: '₱' };
        try {
            return JSON.parse(el.textContent);
        } catch (error) {
            console.error('Could not parse reports config:', error);
            return { currencySymbol: '₱' };
        }
    }

    const currencySymbol = config().currencySymbol || '₱';

    /**
     * Draw a Chart.js chart, or show a placeholder if the library is missing.
     *
     * Chart.js is loaded from a CDN. On a shop with unreliable internet that
     * script can simply fail, and calling `new Chart(...)` then throws a
     * ReferenceError that aborts the surrounding handler - taking the tables
     * and totals down with it. Degrade to a message instead.
     */
    function renderChart(canvasId, chartConfig) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) return null;

        if (typeof Chart === 'undefined') {
            const container = canvas.parentElement || canvas;
            container.innerHTML =
                '<div class="flex items-center justify-center h-full text-sm text-gray-400 py-8">' +
                '<i class="fas fa-chart-line mr-2"></i>Charts unavailable offline</div>';
            return null;
        }

        return new Chart(canvas.getContext('2d'), chartConfig);
    }

    // Helper function to get payment method badge
    function getPaymentBadge(method) {
        const badges = {
            cash: '<span class="px-2 py-1 text-xs rounded-full bg-green-100 text-green-800">Cash</span>',
            card: '<span class="px-2 py-1 text-xs rounded-full bg-blue-100 text-blue-800">Card</span>',
            gcash: '<span class="px-2 py-1 text-xs rounded-full bg-purple-100 text-purple-800">GCash</span>',
            paymaya: '<span class="px-2 py-1 text-xs rounded-full bg-orange-100 text-orange-800">PayMaya</span>',
        };
        return badges[method] || '<span class="px-2 py-1 text-xs rounded-full bg-gray-100 text-gray-800">Other</span>';
    }

    // Load today's sales data
    function loadTodaysSales() {
        fetch('/api/dashboard/today')
            .then(function (response) { return response.json(); })
            .then(function (data) {
                // Update today's sales card with null checks
                const totalRevenue = (data && data.total_revenue) || 0;
                const totalSales = (data && data.total_sales) || 0;

                document.getElementById('todaysRevenue').textContent =
                    currencySymbol + totalRevenue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                document.getElementById('todaysSalesCount').textContent = totalSales.toLocaleString();

                // Set today's date
                const today = new Date();
                document.getElementById('todayDate').textContent = today.toLocaleDateString('en-US', {
                    weekday: 'long',
                    year: 'numeric',
                    month: 'long',
                    day: 'numeric',
                });

                // Update today's sales table
                const todaysSalesTableBody = document.getElementById('todaysSalesTableBody');
                const sales = (data && data.sales) || [];

                if (sales.length === 0) {
                    todaysSalesTableBody.innerHTML = `
                        <tr>
                            <td colspan="5" class="text-center py-8 text-gray-500">
                                <i class="fas fa-info-circle mr-2"></i>No sales recorded today
                            </td>
                        </tr>
                    `;
                } else {
                    todaysSalesTableBody.innerHTML = sales.map(function (sale) {
                        return `
                        <tr class="border-b hover:bg-gray-50">
                            <td class="py-3 px-2">${sale.sale_date ? new Date(sale.sale_date).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }) : 'N/A'}</td>
                            <td class="py-3 px-2">${JRF.escapeHtml(sale.customer_name || 'Walk-in Customer')}</td>
                            <td class="py-3 px-2 text-right font-semibold">${currencySymbol}${(sale.total_amount || 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                            <td class="py-3 px-2">${getPaymentBadge(sale.payment_method || 'cash')}</td>
                            <td class="py-3 px-2">${JRF.escapeHtml(sale.staff_name || 'Unknown')}</td>
                        </tr>
                        `;
                    }).join('');
                }
            })
            .catch(function (error) {
                console.error("Error loading today's sales:", error);
                document.getElementById('todaysSalesTableBody').innerHTML = `
                    <tr>
                        <td colspan="5" class="text-center py-8 text-red-500">
                            <i class="fas fa-exclamation-triangle mr-2"></i>Error loading today's sales data
                        </td>
                    </tr>
                `;
            });
    }

    // Export reports function
    function exportReports() {
        const dateRange = document.getElementById('dateRange').value;

        // Create export data
        const exportData = {
            dateRange: dateRange,
            timestamp: new Date().toISOString(),
        };

        // In a real app, this would generate and download a CSV/PDF report
        // For now, we'll show an alert
        alert(`Exporting reports for the last ${dateRange} days...\n\nThis is a demo - actual export would generate a downloadable file.`);

        // Simulate export (in real app, this would make an API call)
        console.log('Exporting reports:', exportData);
    }

    document.addEventListener('click', function (event) {
        if (event.target.closest('.js-export-reports')) {
            exportReports();
        }
    });

    // Load real sales data from API
    fetch('/api/dashboard/overview')
        .then(function (response) { return response.json(); })
        .then(function (data) {
            // Update summary cards with real data
            document.getElementById('totalRevenue').textContent =
                currencySymbol + data.statistics.total_revenue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            document.getElementById('totalSales').textContent = data.statistics.total_sales.toLocaleString();
            document.getElementById('lowStockItems').textContent = data.statistics.low_stock_parts.toLocaleString();

            // Load today's sales data
            loadTodaysSales();

            // Update top products table with all records
            const topProductsTableBody = document.getElementById('topProductsTableBody');
            document.getElementById('topProductsCount').textContent = data.top_parts.length;

            if (data.top_parts.length === 0) {
                topProductsTableBody.innerHTML = `
                    <tr>
                        <td colspan="3" class="text-center py-8 text-gray-500">
                            <i class="fas fa-info-circle mr-2"></i>No sales data available
                        </td>
                    </tr>
                `;
            } else {
                topProductsTableBody.innerHTML = data.top_parts.map(function (part) {
                    return `
                    <tr class="border-b hover:bg-gray-50">
                        <td class="py-3 px-2 font-medium">${JRF.escapeHtml(part.name)}</td>
                        <td class="py-3 px-2 text-right">${part.total_sold}</td>
                        <td class="py-3 px-2 text-right font-semibold">${currencySymbol}${part.total_revenue.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                    </tr>
                    `;
                }).join('');
            }

            // Update low stock items table
            const lowStockTableBody = document.getElementById('lowStockTableBody');
            document.getElementById('lowStockCount').textContent = data.low_stock_items.length;

            if (data.low_stock_items.length === 0) {
                lowStockTableBody.innerHTML = `
                    <tr>
                        <td colspan="3" class="text-center py-8 text-green-600">
                            <i class="fas fa-check-circle mr-2"></i>All items are well stocked
                        </td>
                    </tr>
                `;
            } else {
                lowStockTableBody.innerHTML = data.low_stock_items.map(function (item) {
                    const urgencyColor = item.stock_quantity === 0 ? 'bg-red-100 text-red-800' : 'bg-yellow-100 text-yellow-800';
                    return `
                        <tr class="border-b hover:bg-gray-50">
                            <td class="py-3 px-2 font-medium">${JRF.escapeHtml(item.name)}</td>
                            <td class="py-3 px-2 text-center">
                                <span class="px-2 py-1 text-xs rounded-full ${urgencyColor}">
                                    ${item.stock_quantity}
                                </span>
                            </td>
                            <td class="py-3 px-2 text-right">${currencySymbol}${item.price.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                        </tr>
                    `;
                }).join('');
            }

            // Process sales by day data for chart
            const salesLabels = data.sales_by_day.map(function (item) {
                const date = new Date(item.date);
                return date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
            });
            const salesValues = data.sales_by_day.map(function (item) { return item.total; });

            const salesData = {
                labels: salesLabels,
                datasets: [{
                    label: 'Sales',
                    data: salesValues,
                    borderColor: 'rgb(59, 130, 246)',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    tension: 0.4,
                }],
            };

            // Initialize sales chart. Chart.js comes from a CDN, so guard
            // against it being unreachable - the rest of the report is still
            // useful without the graph, and an uncaught ReferenceError here
            // would abort the whole handler and blank the page.
            renderChart('salesChart', {
                type: 'line',
                data: salesData,
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            display: false,
                        },
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: {
                                callback: function (value) {
                                    return currencySymbol + value.toLocaleString();
                                },
                            },
                        },
                    },
                },
            });

            // Update revenue by category chart
            const categoryLabels = data.revenue_by_category.map(function (item) { return item.category; });
            const categoryValues = data.revenue_by_category.map(function (item) { return item.revenue; });

            const categoryData = {
                labels: categoryLabels,
                datasets: [{
                    data: categoryValues,
                    backgroundColor: [
                        '#3B82F6',
                        '#10B981',
                        '#F59E0B',
                        '#EF4444',
                        '#8B5CF6',
                    ],
                }],
            };

            // Initialize category chart (see the note above about the CDN).
            renderChart('categoryChart', {
                type: 'doughnut',
                data: categoryData,
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'bottom',
                        },
                    },
                },
            });
        })
        .catch(function (error) {
            console.error('Error loading sales data:', error);
            // Show error messages in all tables
            document.getElementById('topProductsTableBody').innerHTML = `
                <tr>
                    <td colspan="3" class="text-center py-8 text-red-500">
                        <i class="fas fa-exclamation-triangle mr-2"></i>Error loading products data
                    </td>
                </tr>
            `;
            document.getElementById('lowStockTableBody').innerHTML = `
                <tr>
                    <td colspan="3" class="text-center py-8 text-red-500">
                        <i class="fas fa-exclamation-triangle mr-2"></i>Error loading low stock data
                    </td>
                </tr>
            `;
        });
})();
