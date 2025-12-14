#!/usr/bin/env python3
"""
Comprehensive MySQL integration test script
"""

from app import app, db, Supplier, Part, Customer, Sale, Expense, MaintenanceLog, Notification

def test_mysql_integration():
    """Test all MySQL database integration components"""
    with app.app_context():
        print("🔍 TESTING MYSQL DATABASE INTEGRATION...")
        
        # Test 1: Database Models
        print("\n1. TESTING DATABASE MODELS:")
        try:
            suppliers = Supplier.query.all()
            parts = Part.query.all()
            customers = Customer.query.all()
            sales = Sale.query.all()
            expenses = Expense.query.all()
            maintenance = MaintenanceLog.query.all()
            notifications = Notification.query.all()
            
            print(f"   ✅ Suppliers: {len(suppliers)}")
            print(f"   ✅ Parts: {len(parts)}")
            print(f"   ✅ Customers: {len(customers)}")
            print(f"   ✅ Sales: {len(sales)}")
            print(f"   ✅ Expenses: {len(expenses)}")
            print(f"   ✅ Maintenance: {len(maintenance)}")
            print(f"   ✅ Notifications: {len(notifications)}")
        except Exception as e:
            print(f"   ❌ Database Models Error: {e}")
        
        # Test 2: Data Relationships
        print("\n2. TESTING DATA RELATIONSHIPS:")
        try:
            suppliers_with_parts = Supplier.query.filter(Supplier.parts.any()).all()
            customers_with_sales = Customer.query.filter(Customer.sales.any()).all()
            parts_with_maintenance = Part.query.filter(Part.maintenance_logs.any()).all()
            
            print(f"   ✅ Suppliers with parts: {len(suppliers_with_parts)}")
            print(f"   ✅ Customers with sales: {len(customers_with_sales)}")
            print(f"   ✅ Parts with maintenance: {len(parts_with_maintenance)}")
        except Exception as e:
            print(f"   ❌ Data Relationships Error: {e}")
        
        # Test 3: API Endpoints
        print("\n3. TESTING API ENDPOINTS:")
        with app.test_client() as client:
            endpoints = [
                ('/api/realtime/inventory', 'Inventory'),
                ('/api/realtime/sales', 'Sales'),
                ('/api/todays-sales', "Today's Sales"),
                ('/api/suppliers', 'Suppliers'),
                ('/api/parts', 'Parts'),
                ('/api/customers', 'Customers'),
                ('/api/expenses', 'Expenses'),
                ('/api/maintenance-logs', 'Maintenance'),
                ('/api/notifications', 'Notifications')
            ]
            
            for endpoint, name in endpoints:
                try:
                    response = client.get(endpoint)
                    if response.status_code == 200:
                        data = response.get_json()
                        if isinstance(data, list):
                            print(f"   ✅ {name}: {len(data)} items")
                        elif isinstance(data, dict):
                            if 'sales' in data:
                                print(f"   ✅ {name}: {len(data.get('sales', []))} sales")
                            else:
                                print(f"   ✅ {name}: Data returned")
                        else:
                            print(f"   ✅ {name}: Response OK")
                    elif response.status_code == 302:
                        print(f"   ⚠️ {name}: Requires login (302)")
                    else:
                        print(f"   ❌ {name}: Status {response.status_code}")
                except Exception as e:
                    print(f"   ❌ {name} Error: {e}")
        
        # Test 4: Data Consistency
        print("\n4. TESTING DATA CONSISTENCY:")
        try:
            # Check Part model has updated_at
            parts = Part.query.all()
            if parts and parts[0].updated_at:
                print(f"   ✅ Parts have updated_at timestamps")
            else:
                print(f"   ❌ Parts missing updated_at timestamps")
            
            # Check sales have customer relationships
            sales_with_customers = Sale.query.filter(Sale.customer_id.isnot(None)).count()
            total_sales = Sale.query.count()
            print(f"   ✅ Sales with customers: {sales_with_customers}/{total_sales}")
            
            # Check maintenance has part relationships
            maintenance_with_parts = MaintenanceLog.query.filter(MaintenanceLog.part_id.isnot(None)).count()
            total_maintenance = MaintenanceLog.query.count()
            print(f"   ✅ Maintenance with parts: {maintenance_with_parts}/{total_maintenance}")
            
        except Exception as e:
            print(f"   ❌ Data Consistency Error: {e}")
        
        # Test 5: Real-time Features
        print("\n5. TESTING REAL-TIME FEATURES:")
        try:
            # Test Part updated_at functionality
            part = Part.query.first()
            if part:
                original_updated_at = part.updated_at
                part.stock_quantity = part.stock_quantity + 1
                db.session.commit()
                
                updated_part = db.session.get(Part, part.id)
                if updated_part.updated_at > original_updated_at:
                    print(f"   ✅ Part updated_at timestamp working")
                else:
                    print(f"   ❌ Part updated_at timestamp not updating")
        except Exception as e:
            print(f"   ❌ Real-time Features Error: {e}")
        
        print("\n✅ MYSQL INTEGRATION TEST COMPLETE!")

if __name__ == "__main__":
    test_mysql_integration()
