/**
 * Inventory report page: low-stock table and a by-category valuation table.
 *
 * Previously inline in reports_inventory.html - blocked outright under the
 * production CSP (no 'unsafe-inline' in script-src).
 *
 * Security fix made while converting: the category table interpolated
 * `p.part_type` (aliased to `cat`) straight into innerHTML with no
 * escaping. `part_type` is a free-text field (up to 50 chars, no enum
 * constraint - see Part.part_type / PartSchema in app/schemas/__init__.py)
 * settable by any staff member through the Add/Edit Part form, so an
 * attacker with product-management access could store an HTML/script
 * payload as a "category" and have it execute for every viewer of this
 * report. It is now run through JRF.escapeHtml like every other
 * user-controlled field on this page (part name, SKU).
 */
(function () {
    'use strict';

    async function loadInventoryReport() {
        try {
            // Load low stock items
            const response = await fetch('/api/parts/low-stock');
            if (response.ok) {
                const parts = await response.json();
                let html = '<table class="min-w-full"><thead><tr class="text-left text-xs font-medium text-gray-500 uppercase"><th class="pb-2">Part</th><th class="pb-2">SKU</th><th class="pb-2 text-right">Stock</th><th class="pb-2">Status</th></tr></thead><tbody class="border-t border-gray-200">';
                parts.forEach(function (p) {
                    let status = 'low';
                    let cls = 'badge-low';
                    if (p.stock_quantity <= 0) {
                        status = 'out_of_stock';
                        cls = 'badge-low';
                    } else if (p.stock_quantity >= p.min_stock_level * 2) {
                        status = 'ok';
                        cls = 'badge-ok';
                    } else if (p.stock_quantity >= p.min_stock_level) {
                        status = 'moderate';
                        cls = 'badge-moderate';
                    }
                    html += `<tr class="table-row"><td class="py-2 font-medium">${JRF.escapeHtml(p.name)}</td><td class="py-2 text-sm text-gray-500">${JRF.escapeHtml(p.sku || '')}</td><td class="py-2 text-right">${p.stock_quantity}</td><td class="py-2"><span class="badge ${cls}">${status.replace('_', ' ')}</span></td></tr>`;
                });
                html += '</tbody></table>';
                document.querySelector('#low-stock-table').innerHTML = html;
            }
        } catch (e) {
            console.error(e);
        }

        try {
            // Load full inventory for category analysis
            const response2 = await fetch('/api/parts?per_page=100');
            if (response2.ok) {
                const data = await response2.json();
                const parts = data.parts || [];
                const categories = {};
                let totalValue = 0;

                parts.forEach(function (p) {
                    const cat = p.part_type || 'Other';
                    if (!categories[cat]) categories[cat] = { count: 0, value: 0 };
                    categories[cat].count += 1;
                    categories[cat].value += (p.price || 0) * p.stock_quantity;
                    totalValue += (p.price || 0) * p.stock_quantity;
                });

                let html = '<table class="min-w-full"><thead><tr class="text-left text-xs font-medium text-gray-500 uppercase"><th class="pb-2">Category</th><th class="pb-2 text-right">Items</th><th class="pb-2 text-right">Value</th></tr></thead><tbody class="border-t border-gray-200">';
                for (const [cat, d] of Object.entries(categories)) {
                    html += `<tr class="table-row"><td class="py-2 font-medium">${JRF.escapeHtml(cat)}</td><td class="py-2 text-right">${d.count}</td><td class="py-2 text-right">₱${d.value.toFixed(2)}</td></tr>`;
                }
                html += `</tbody><tfoot><tr class="border-t-2"><td class="py-2 font-bold">Total</td><td class="py-2 text-right font-bold">${Object.values(categories).reduce(function (s, c) { return s + c.count; }, 0)}</td><td class="py-2 text-right font-bold">₱${totalValue.toFixed(2)}</td></tr></tfoot></table>`;
                document.querySelector('#category-table').innerHTML = html;
            }
        } catch (e) {
            console.error(e);
        }
    }

    function exportInventory() {
        alert('Export functionality will be available soon.');
    }

    document.addEventListener('click', function (event) {
        if (event.target.closest('.js-export-inventory')) {
            exportInventory();
        }
    });

    document.addEventListener('DOMContentLoaded', loadInventoryReport);
})();
