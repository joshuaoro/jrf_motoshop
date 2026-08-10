/**
 * Sale detail page: "Print Invoice" button.
 *
 * sale_detail.html previously called this inline as onclick="printInvoice()",
 * which the production CSP blocks outright (no 'unsafe-inline' in
 * script-src). While moving it out we found printInvoice() was never
 * defined anywhere in the codebase - templates, base_new.html, or any
 * static JS file - so the button has always thrown a ReferenceError when
 * clicked, CSP or not. Implemented here as a plain window.print(), which is
 * what "print invoice" means for a page that already renders as a
 * printable receipt.
 */
document.addEventListener('click', function (event) {
    if (event.target.closest('.js-print-invoice')) {
        window.print();
    }
});
