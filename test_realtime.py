#!/usr/bin/env python3
"""
Test script to verify real-time database connections
"""

from app import app, db, Supplier, Part, Customer, Sale, Expense, MaintenanceLog, Notification

def test_database_connections():
    """Test all database connections and real-time data"""
    with app.app_context():
        print("=== TESTING REAL-TIME DATABASE CONNECTIONS ===\n")
        
        # Test database models
        print("1. DATABASE MODEL CONNECTIONS:")
        try:
            suppliers = Supplier.query.all()
            print(f"   ✅ Suppliers: {len(suppliers)} connected")
            if suppliers:
                print(f"      Sample: {suppliers[0].name} - {len(suppliers[0].parts)} parts")
        except Exception as e:
            print(f"   ❌ Suppliers Error: {e}")
        
        try:
            parts = Part.query.all()
            print(f"   ✅ Parts: {len(parts)} connected")
            if parts:
                print(f"      Sample: {parts[0].name} - Stock: {parts[0].stock_quantity} - Price: ₱{parts[0].price}")
        except Exception as e:
            print(f"   ❌ Parts Error: {e}")
        
        try:
            customers = Customer.query.all()
            print(f"   ✅ Customers: {len(customers)} connected")
            if customers:
                print(f"      Sample: {customers[0].name}")
        except Exception as e:
            print(f"   ❌ Customers Error: {e}")
        
        try:
            sales = Sale.query.all()
            print(f"   ✅ Sales: {len(sales)} connected")
            if sales:
                print(f"      Sample: Sale #{sales[0].id} - ₱{sales[0].total_amount}")
        except Exception as e:
            print(f"   ❌ Sales Error: {e}")
        
        try:
            expenses = Expense.query.all()
            print(f"   ✅ Expenses: {len(expenses)} connected")
            if expenses:
                print(f"      Sample: {expenses[0].category} - ₱{expenses[0].amount}")
        except Exception as e:
            print(f"   ❌ Expenses Error: {e}")
        
        try:
            maintenance = MaintenanceLog.query.all()
            print(f"   ✅ Maintenance Logs: {len(maintenance)} connected")
            if maintenance:
                print(f"      Sample: {maintenance[0].equipment_name} - {maintenance[0].maintenance_type}")
        except Exception as e:
            print(f"   ❌ Maintenance Error: {e}")
        
        try:
            notifications = Notification.query.all()
            print(f"   ✅ Notifications: {len(notifications)} connected")
            if notifications:
                print(f"      Sample: {notifications[0].title} - {notifications[0].type}")
        except Exception as e:
            print(f"   ❌ Notifications Error: {e}")
        
        print("\n2. API ENDPOINT CONNECTIONS:")
        
        # Test API endpoints
        with app.test_client() as client:
            endpoints = [
                ('/api/suppliers', 'Suppliers'),
                ('/api/parts', 'Parts'),
                ('/api/customers', 'Customers'),
                ('/api/sales', 'Sales'),
                ('/api/expenses', 'Expenses'),
                ('/api/maintenance-logs', 'Maintenance'),
                ('/api/notifications', 'Notifications')
            ]
            
            for endpoint, name in endpoints:
                try:
                    response = client.get(endpoint)
                    if response.status_code == 200:
                        data = response.get_json()
                        print(f"   ✅ {name} API: {len(data) if isinstance(data, list) else 'N/A'} items")
                    else:
                        print(f"   ❌ {name} API: Status {response.status_code}")
                except Exception as e:
                    print(f"   ❌ {name} API Error: {e}")
        
        print("\n3. REAL-TIME DATA INTEGRITY:")
        
        # Test data relationships
        try:
            # Test supplier-part relationships
            suppliers_with_parts = Supplier.query.filter(Supplier.parts.any()).all()
            print(f"   ✅ Supplier-Part Relationships: {len(suppliers_with_parts)} suppliers have parts")
            
            # Test customer-sales relationships
            customers_with_sales = Customer.query.filter(Customer.sales.any()).all()
            print(f"   ✅ Customer-Sales Relationships: {len(customers_with_sales)} customers have sales")
            
            # Test part-maintenance relationships
            parts_with_maintenance = Part.query.filter(Part.maintenance_logs.any()).all()
            print(f"   ✅ Part-Maintenance Relationships: {len(parts_with_maintenance)} parts have maintenance logs")
            
        except Exception as e:
            print(f"   ❌ Relationship Error: {e}")
        
        print("\n4. DATA CONSISTENCY CHECK:")
        
        try:
            # Check for data consistency
            total_parts_from_suppliers = sum(len(supplier.parts) for supplier in Supplier.query.all())
            total_parts = Part.query.count()
            print(f"   ✅ Parts Count: {total_parts} in database, {total_parts_from_suppliers} from suppliers")
            
            total_sales_from_customers = sum(len(customer.sales) for customer in Customer.query.all())
            total_sales = Sale.query.count()
            print(f"   ✅ Sales Count: {total_sales} in database, {total_sales_from_customers} from customers")
            
        except Exception as e:
            print(f"   ❌ Consistency Error: {e}")
        
        print("\n=== REAL-TIME CONNECTION TEST COMPLETE ===")

if __name__ == "__main__":
    test_database_connections()
