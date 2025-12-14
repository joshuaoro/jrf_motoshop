// Real-time Database Integration Utility
// This script provides real-time data synchronization with MySQL database

class RealtimeDB {
    constructor() {
        this.refreshInterval = 30000; // 30 seconds
        this.intervals = {};
        this.callbacks = {};
    }

    // Initialize real-time updates for a specific page
    init(pageType, callbacks = {}) {
        this.callbacks = callbacks;
        
        // Clear any existing intervals
        this.clearAllIntervals();
        
        // Set up page-specific real-time updates
        switch(pageType) {
            case 'dashboard':
                this.setupDashboardUpdates();
                break;
            case 'inventory':
                this.setupInventoryUpdates();
                break;
            case 'sales':
                this.setupSalesUpdates();
                break;
            case 'customers':
                this.setupCustomersUpdates();
                break;
            case 'notifications':
                this.setupNotificationsUpdates();
                break;
            case 'reports':
                this.setupReportsUpdates();
                break;
        }
        
        console.log(`Real-time updates initialized for ${pageType}`);
    }

    // Dashboard real-time updates
    setupDashboardUpdates() {
        // Update stats every 30 seconds
        this.intervals.stats = setInterval(() => {
            this.fetch('/api/realtime/stats')
                .then(data => {
                    this.updateDashboardStats(data);
                    if (this.callbacks.onStatsUpdate) {
                        this.callbacks.onStatsUpdate(data);
                    }
                })
                .catch(error => console.error('Error updating stats:', error));
        }, this.refreshInterval);

        // Update activities every 30 seconds
        this.intervals.activities = setInterval(() => {
            this.fetch('/api/realtime/activities')
                .then(data => {
                    this.updateActivities(data);
                    if (this.callbacks.onActivitiesUpdate) {
                        this.callbacks.onActivitiesUpdate(data);
                    }
                })
                .catch(error => console.error('Error updating activities:', error));
        }, this.refreshInterval);
    }

    // Inventory real-time updates
    setupInventoryUpdates() {
        this.intervals.inventory = setInterval(() => {
            this.fetch('/api/realtime/inventory')
                .then(data => {
                    this.updateInventoryTable(data);
                    if (this.callbacks.onInventoryUpdate) {
                        this.callbacks.onInventoryUpdate(data);
                    }
                })
                .catch(error => console.error('Error updating inventory:', error));
        }, this.refreshInterval);
    }

    // Sales real-time updates
    setupSalesUpdates() {
        this.intervals.sales = setInterval(() => {
            this.fetch('/api/realtime/sales')
                .then(data => {
                    this.updateSalesTable(data);
                    if (this.callbacks.onSalesUpdate) {
                        this.callbacks.onSalesUpdate(data);
                    }
                })
                .catch(error => console.error('Error updating sales:', error));
        }, this.refreshInterval);
    }

    // Notifications real-time updates
    setupNotificationsUpdates() {
        this.intervals.notifications = setInterval(() => {
            this.fetch('/api/realtime/notifications')
                .then(data => {
                    this.updateNotificationsList(data);
                    this.updateNotificationBadge(data.length);
                    if (this.callbacks.onNotificationsUpdate) {
                        this.callbacks.onNotificationsUpdate(data);
                    }
                })
                .catch(error => console.error('Error updating notifications:', error));
        }, this.refreshInterval);
    }

    // Customers real-time updates
    setupCustomersUpdates() {
        this.intervals.customers = setInterval(() => {
            this.fetch('/api/realtime/customers')
                .then(data => {
                    this.updateCustomersTable(data);
                    if (this.callbacks.onCustomersUpdate) {
                        this.callbacks.onCustomersUpdate(data);
                    }
                })
                .catch(error => console.error('Error updating customers:', error));
        }, this.refreshInterval);
    }

    // Reports real-time updates
    setupReportsUpdates() {
        this.intervals.reports = setInterval(() => {
            this.fetch('/api/realtime/stats')
                .then(data => {
                    this.updateReportsStats(data);
                    if (this.callbacks.onReportsUpdate) {
                        this.callbacks.onReportsUpdate(data);
                    }
                })
                .catch(error => console.error('Error updating reports:', error));
        }, this.refreshInterval * 2); // Update reports every minute
    }

    // UI Update Methods
    updateDashboardStats(data) {
        // Update dashboard stat cards
        const elements = {
            'totalParts': data.total_parts,
            'lowStockItems': data.low_stock_parts,
            'totalSales': data.total_sales,
            'totalSuppliers': data.total_suppliers,
            'totalCustomers': data.total_customers,
            'todayRevenue': data.today_revenue
        };

        Object.keys(elements).forEach(key => {
            const element = document.getElementById(key);
            if (element) {
                if (key === 'todayRevenue') {
                    element.textContent = this.formatCurrency(elements[key]);
                } else {
                    element.textContent = elements[key].toLocaleString();
                }
            }
        });
    }

    updateActivities(activities) {
        const activitiesContainer = document.getElementById('recentActivities');
        if (!activitiesContainer) return;

        activitiesContainer.innerHTML = activities.map(activity => `
            <div class="flex items-center p-3 bg-gray-50 rounded-lg">
                <div class="flex-shrink-0">
                    <div class="w-8 h-8 ${activity.icon_bg} rounded-full flex items-center justify-center">
                        <i class="${activity.icon} text-white text-xs"></i>
                    </div>
                </div>
                <div class="ml-3">
                    <p class="text-sm text-gray-600">${activity.message}</p>
                    <p class="text-xs text-gray-500">${this.formatTime(activity.timestamp)}</p>
                </div>
            </div>
        `).join('');
    }

    updateInventoryTable(parts) {
        const tbody = document.querySelector('#inventoryTable tbody');
        if (!tbody) return;

        parts.forEach(part => {
            const row = document.querySelector(`tr[data-id="${part.id}"]`);
            if (row) {
                const stockCell = row.querySelector('.stock-quantity');
                if (stockCell) {
                    stockCell.textContent = part.stock_quantity;
                    // Update stock status color
                    const stockBadge = stockCell.parentElement.querySelector('.stock-badge');
                    if (stockBadge) {
                        stockBadge.className = `stock-badge ${this.getStockStatusClass(part.stock_quantity)}`;
                    }
                }
            }
        });
    }

    updateSalesTable(sales) {
        const tbody = document.querySelector('#recentSalesTable tbody');
        if (!tbody) return;

        tbody.innerHTML = sales.map(sale => `
            <tr>
                <td>${sale.id}</td>
                <td>${this.formatCurrency(sale.total_amount)}</td>
                <td>${sale.payment_method}</td>
                <td>${sale.staff_name}</td>
                <td>${this.formatTime(sale.created_at)}</td>
            </tr>
        `).join('');
    }

    updateNotificationsList(notifications) {
        const container = document.getElementById('notificationsList');
        if (!container) return;

        container.innerHTML = notifications.map(notification => `
            <div class="notification-item p-3 border-b hover:bg-gray-50 ${notification.type}">
                <div class="flex justify-between items-start">
                    <div>
                        <h4 class="font-medium text-gray-800">${notification.title}</h4>
                        <p class="text-sm text-gray-600">${notification.message}</p>
                        <p class="text-xs text-gray-500 mt-1">${this.formatTime(notification.created_at)}</p>
                    </div>
                    ${notification.action_url ? `<a href="${notification.action_url}" class="text-blue-600 hover:text-blue-800 text-sm">View</a>` : ''}
                </div>
            </div>
        `).join('');
    }

    updateNotificationBadge(count) {
        const badge = document.getElementById('notificationBadge');
        if (badge) {
            badge.textContent = count;
            badge.style.display = count > 0 ? 'block' : 'none';
        }
    }

    updateCustomersTable(customers) {
        const tbody = document.querySelector('#customersTable tbody');
        if (!tbody) return;

        customers.forEach(customer => {
            const row = document.querySelector(`tr[data-id="${customer.id}"]`);
            if (row) {
                const salesCell = row.querySelector('.customer-sales');
                const spentCell = row.querySelector('.customer-spent');
                if (salesCell) salesCell.textContent = customer.total_sales;
                if (spentCell) spentCell.textContent = this.formatCurrency(customer.total_spent);
            }
        });
    }

    updateReportsStats(data) {
        // Update reports statistics
        const revenueEl = document.getElementById('totalRevenue');
        if (revenueEl) {
            revenueEl.textContent = this.formatCurrency(data.today_revenue);
        }
    }

    // Utility Methods
    formatCurrency(amount) {
        // Get currency symbol from settings (could be passed from template)
        const currencySymbol = '₱'; // Default, should come from settings
        return currencySymbol + amount.toLocaleString(undefined, {minimumFractionDigits: 2});
    }

    formatTime(timestamp) {
        const date = new Date(timestamp);
        const now = new Date();
        const diff = now - date;
        
        if (diff < 60000) return 'Just now';
        if (diff < 3600000) return Math.floor(diff / 60000) + ' minutes ago';
        if (diff < 86400000) return Math.floor(diff / 3600000) + ' hours ago';
        return date.toLocaleDateString();
    }

    getStockStatusClass(quantity) {
        if (quantity === 0) return 'stock-out';
        if (quantity <= 5) return 'stock-low';
        return 'stock-high';
    }

    // Fetch utility with error handling
    async fetch(url, options = {}) {
        try {
            const response = await fetch(url, {
                ...options,
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers
                }
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            return await response.json();
        } catch (error) {
            console.error(`Fetch error for ${url}:`, error);
            throw error;
        }
    }

    // Clear all intervals
    clearAllIntervals() {
        Object.keys(this.intervals).forEach(key => {
            clearInterval(this.intervals[key]);
        });
        this.intervals = {};
    }

    // Manual refresh method
    refresh(pageType) {
        switch(pageType) {
            case 'dashboard':
                this.fetch('/api/realtime/stats').then(data => this.updateDashboardStats(data));
                this.fetch('/api/realtime/activities').then(data => this.updateActivities(data));
                break;
            case 'inventory':
                this.fetch('/api/realtime/inventory').then(data => this.updateInventoryTable(data));
                break;
            case 'sales':
                this.fetch('/api/realtime/sales').then(data => this.updateSalesTable(data));
                break;
            case 'customers':
                this.fetch('/api/realtime/customers').then(data => this.updateCustomersTable(data));
                break;
            case 'notifications':
                this.fetch('/api/realtime/notifications').then(data => {
                    this.updateNotificationsList(data);
                    this.updateNotificationBadge(data.length);
                });
                break;
        }
    }

    // Destroy method to clean up
    destroy() {
        this.clearAllIntervals();
        this.callbacks = {};
    }
}

// Global instance
window.realtimeDB = new RealtimeDB();

// Auto-initialize based on current page
document.addEventListener('DOMContentLoaded', function() {
    const pageType = document.body.getAttribute('data-page');
    if (pageType) {
        window.realtimeDB.init(pageType);
    }
});
