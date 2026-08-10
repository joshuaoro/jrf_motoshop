/**
 * Sales report page: revenue summary, top products, and a recent-sales
 * table, refreshed every minute.
 *
 * Previously inline in reports_sales.html - blocked outright under the
 * production CSP (no 'unsafe-inline' in script-src).
 */
(function () {
    'use strict';

    async function loadSalesData() {
        try {
            const response = await fetch('/api/sales/summary');
            if (!response.ok) return;
            const summary = await response.json();

            document.querySelector('#activity-chart').innerHTML = `
                <div class="text-center py-8">
                    <div class="text-2xl font-bold text-gray-800">₱${summary.total_revenue || 0}</div>
                    <p class="text-sm text-gray-500 mt-1">Total Revenue</p>
                    <p class="text-sm text-gray-500">${summary.total_sales || 0} transactions</p>
                </div>
            `;

            const response2 = await fetch('/api/sales/top-parts?limit=5');
            if (!response2.ok) return;
            const parts = await response2.json();

            let html = '';
            parts.forEach(function (p, i) {
                html += `<div class="flex items-center justify-between py-2 border-b">
                    <span class="font-medium">#${i + 1} ${JRF.escapeHtml(p.name)}</span>
                    <span class="text-gray-600">${p.total_sold} sold • ₱${p.total_revenue.toFixed(2)}</span>
                </div>`;
            });
            document.querySelector('#top-products-chart').innerHTML = html || '<p class="text-gray-500">No data</p>';

            const response3 = await fetch('/api/realtime/sales?limit=10');
            if (!response3.ok) return;
            const sales = await response3.json();

            let tableHtml = '<table class="min-w-full"><thead><tr class="text-left text-xs font-medium text-gray-500 uppercase"><th class="pb-2">Date</th><th class="pb-2">Receipt</th><th class="pb-2">Amount</th><th class="pb-2">Status</th></tr></thead><tbody class="border-t border-gray-200">';
            sales.forEach(function (s) {
                tableHtml += `<tr class="table-row"><td class="py-2 text-sm">${s.sale_date?.split('T')[0] || ''}</td><td class="py-2 font-medium">${JRF.escapeHtml(s.receipt_number || '')}</td><td class="py-2 text-right">₱${s.total_amount?.toFixed(2) || 0}</td><td class="py-2"><span class="badge bg-blue-100 text-blue-800">${JRF.escapeHtml(s.payment_status || 'paid')}</span></td></tr>`;
            });
            tableHtml += '</tbody></table>';
            document.querySelector('#recent-sales-table').innerHTML = tableHtml;
        } catch (error) {
            console.error('Error loading sales data:', error);
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        loadSalesData();
        setInterval(loadSalesData, 60000);
    });
})();
