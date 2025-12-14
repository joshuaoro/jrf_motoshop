#!/usr/bin/env python3
"""
Database schema update script to add missing columns and optimize real-time data accessibility
"""

from app import app, db
from sqlalchemy import text

def update_database_schema():
    """Update database schema to match current models"""
    with app.app_context():
        print("🔧 Updating database schema...")
        
        try:
            # Add missing columns if they don't exist
            updates = [
                # Add part_id to maintenance_logs if it doesn't exist
                """
                ALTER TABLE maintenance_logs 
                ADD COLUMN part_id INT NULL,
                ADD COLUMN notes TEXT NULL,
                ADD COLUMN next_maintenance DATETIME NULL,
                ADD COLUMN created_by INT NULL;
                """,
                
                # Add foreign key constraints if they don't exist
                """
                ALTER TABLE maintenance_logs 
                ADD CONSTRAINT fk_maintenance_part 
                FOREIGN KEY (part_id) REFERENCES parts(id);
                """,
                
                """
                ALTER TABLE maintenance_logs 
                ADD CONSTRAINT fk_maintenance_creator 
                FOREIGN KEY (created_by) REFERENCES staff(id);
                """
            ]
            
            for i, sql in enumerate(updates, 1):
                try:
                    print(f"Executing update {i}/{len(updates)}...")
                    db.session.execute(text(sql))
                    db.session.commit()
                    print(f"✅ Update {i} completed successfully")
                except Exception as e:
                    if "Duplicate column name" in str(e) or "already exists" in str(e):
                        print(f"⚠️ Update {i} already exists, skipping...")
                        db.session.rollback()
                    else:
                        print(f"❌ Update {i} failed: {e}")
                        db.session.rollback()
            
            # Create sample data if tables are empty
            create_sample_data()
            
            print("✅ Database schema update completed!")
            
        except Exception as e:
            print(f"❌ Database update failed: {e}")
            db.session.rollback()

def create_sample_data():
    """Create sample data to optimize real-time accessibility"""
    print("📊 Creating sample data for real-time optimization...")
    
    from app import Supplier, Part, Customer, Sale, Expense, MaintenanceLog, Notification, User
    
    try:
        # Create suppliers if none exist
        if Supplier.query.count() == 0:
            suppliers_data = [
                Supplier(name="Yamaha Motor Philippines", contact_no="+63 2 8888 9999", address="Makati City"),
                Supplier(name="Honda Parts Center", contact_no="+63 2 7777 8888", address="Quezon City"),
                Supplier(name="Suzuki Accessories", contact_no="+63 2 6666 7777", address="Pasig City"),
                Supplier(name="Kawasaki Motors", contact_no="+63 2 5555 6666", address="Mandaluyong City")
            ]
            for supplier in suppliers_data:
                db.session.add(supplier)
            db.session.commit()
            print("✅ Created sample suppliers")
        
        # Create parts if none exist
        if Part.query.count() == 0:
            parts_data = [
                Part(name="Engine Oil 10W40", brand="Yamalube", part_type="engine", price=350.00, stock=50, reorder_level=10),
                Part(name="Brake Pads Front", brand="Brembo", part_type="brakes", price=1200.00, stock=25, reorder_level=5),
                Part(name="Spark Plug CR9E", brand="NGK", part_type="electrical", price=85.00, stock=100, reorder_level=20),
                Part(name="Air Filter", brand="K&N", part_type="engine", price=450.00, stock=30, reorder_level=8),
                Part(name="Chain 520", brand="RK", part_type="suspension", price=800.00, stock=15, reorder_level=3),
                Part(name="Clutch Cable", brand="Yamaha", part_type="transmission", price=280.00, stock=40, reorder_level=10),
                Part(name="Radiator Hose", brand="Honda", part_type="cooling", price=320.00, stock=20, reorder_level=5),
                Part(name="Turn Signal Light", brand="Suzuki", part_type="electrical", price=150.00, stock=60, reorder_level=15),
                Part(name="Foot Peg", brand="Kawasaki", part_type="body", price=180.00, stock=35, reorder_level=7),
                Part(name="Battery 12V", brand="Motobatt", part_type="electrical", price=1500.00, stock=12, reorder_level=2)
            ]
            for part in parts_data:
                db.session.add(part)
            db.session.commit()
            print("✅ Created sample parts")
        
        # Create supplier-part associations
        suppliers = Supplier.query.all()
        parts = Part.query.all()
        
        if suppliers and parts:
            # Clear existing associations
            db.session.execute(text("DELETE FROM supplier_part"))
            db.session.commit()
            
            # Create new associations
            associations = [
                (suppliers[0], [parts[0], parts[1], parts[5]]),  # Yamaha supplier
                (suppliers[1], [parts[1], parts[6], parts[7]]),  # Honda supplier  
                (suppliers[2], [parts[2], parts[7], parts[8]]),  # Suzuki supplier
                (suppliers[3], [parts[3], parts[4], parts[9]])   # Kawasaki supplier
            ]
            
            for supplier, supplier_parts in associations:
                for part in supplier_parts:
                    supplier.parts.append(part)
            
            db.session.commit()
            print("✅ Created supplier-part associations")
        
        # Create customers if none exist
        if Customer.query.count() == 0:
            customers_data = [
                Customer(name="Juan Dela Cruz", email="juan@email.com", phone="+63 912 345 6789", address="Manila"),
                Customer(name="Maria Santos", email="maria@email.com", phone="+63 923 456 7890", address="Quezon City"),
                Customer(name="Jose Reyes", email="jose@email.com", phone="+63 934 567 8901", address="Makati")
            ]
            for customer in customers_data:
                db.session.add(customer)
            db.session.commit()
            print("✅ Created sample customers")
        
        # Create sample sales
        if Sale.query.count() == 0:
            customers = Customer.query.all()
            parts = Part.query.all()
            
            for i in range(5):
                sale = Sale(
                    customer_id=customers[i % len(customers)].id if customers else None,
                    total_amount=(i + 1) * 500.00,
                    payment_method="cash",
                    sale_date=datetime.utcnow()
                )
                db.session.add(sale)
            
            db.session.commit()
            print("✅ Created sample sales")
        
        # Create sample expenses
        if Expense.query.count() == 0:
            expenses_data = [
                Expense(category="utilities", amount=2500.00, description="Electricity bill", expense_date=datetime.utcnow()),
                Expense(category="supplies", amount=1200.00, description="Office supplies", expense_date=datetime.utcnow()),
                Expense(category="maintenance", amount=800.00, description="Equipment maintenance", expense_date=datetime.utcnow())
            ]
            for expense in expenses_data:
                db.session.add(expense)
            
            db.session.commit()
            print("✅ Created sample expenses")
        
        # Create sample maintenance logs
        if MaintenanceLog.query.count() == 0:
            parts = Part.query.all()
            users = User.query.all()
            
            for i, part in enumerate(parts[:3]):
                maintenance = MaintenanceLog(
                    part_id=part.id,
                    maintenance_type="preventive",
                    equipment_name=f"Equipment {i+1}",
                    description=f"Regular maintenance for {part.name}",
                    cost=200.00,
                    performed_by="Internal Staff",
                    notes="Completed successfully",
                    created_by=users[0].id if users else None,
                    maintenance_date=datetime.utcnow()
                )
                db.session.add(maintenance)
            
            db.session.commit()
            print("✅ Created sample maintenance logs")
        
        # Create sample notifications
        if Notification.query.count() == 0:
            notifications_data = [
                Notification(title="Low Stock Alert", message="Engine Oil is running low", type="warning", category="inventory"),
                Notification(title="New Sale", message="Sale completed successfully", type="success", category="sales"),
                Notification(title="System Update", message="Database optimized", type="info", category="system")
            ]
            for notification in notifications_data:
                db.session.add(notification)
            
            db.session.commit()
            print("✅ Created sample notifications")
        
        print("✅ Sample data creation completed!")
        
    except Exception as e:
        print(f"❌ Sample data creation failed: {e}")
        db.session.rollback()

if __name__ == "__main__":
    update_database_schema()
