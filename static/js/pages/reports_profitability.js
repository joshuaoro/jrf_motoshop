/**
 * Profitability report page: estimated cost/profit per top-selling part.
 *
 * Previously inline in reports_profitability.html - blocked outright under
 * the production CSP (no 'unsafe-inline' in script-src).
 */
(function () {
    'use strict';

    async function loadProfitabilityReport() {
        try {
            const response = await fetch('/api/sales/top-parts?limit=10');
            if (!response.ok) return;
            const parts = await response.json();

            let totalRevenue = 0;
            let html = '<table class="min-w-full"><thead><tr class="text-left text-xs font-medium text-gray-500 uppercase"><th class="pb-2">Part</th><th class="pb-2 text-right">Sold</th><th class="pb-2 text-right">Revenue</th><th class="pb-2 text-right">Est. Profit</th></tr></thead><tbody class="border-t border-gray-200">';

            parts.forEach(function (p) {
                const revenue = p.total_revenue || 0;
                totalRevenue += revenue;
                const estCost = revenue * 0.7; // Estimated 70% cost
                const profit = revenue - estCost;
                html += `<tr class="table-row">
                    <td class="py-2 font-medium">${JRF.escapeHtml(p.name)}</td>
                    <td class="py-2 text-right">${p.total_sold || 0}</td>
                    <td class="py-2 text-right">₱${revenue.toFixed(2)}</td>
                    <td class="py-2 text-right text-green-600 font-medium">₱${profit.toFixed(2)}</td>
                </tr>`;
            });

            html += `</tbody><tfoot><tr class="border-t-2"><td class="py-2 font-bold" colspan="2">Totals</td><td class="py-2 text-right font-bold">₱${totalRevenue.toFixed(2)}</td><td class="py-2 text-right font-bold text-green-600">₱${(totalRevenue * 0.3).toFixed(2)}</td></tr></tfoot></table>`;

            document.querySelector('#profit-items-table').innerHTML = html;
        } catch (error) {
            console.error('Error loading profitability data:', error);
        }
    }

    document.addEventListener('DOMContentLoaded', loadProfitabilityReport);
})();
