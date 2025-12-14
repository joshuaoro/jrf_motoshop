from app import app, db, User, Part, Supplier
from datetime import datetime

def create_tables():
    with app.app_context():
        # Create all database tables
        db.create_all()
        
        # Check if admin user already exists
        admin = User.query.filter_by(email='admin@jrfmotorcycle.com').first()
        
        if not admin:
            # Create default admin user
            admin = User(
                username='admin',
                email='admin@jrfmotorcycle.com',
                name='Administrator',
                role='admin',
                contact_no='+1234567890'
            )
            admin.set_password('admin123')
            
            db.session.add(admin)
            print("Created admin user.")
        
        # Create sample suppliers
        if Supplier.query.count() == 0:
            suppliers = [
                Supplier(
                    name='Yamaha Philippines',
                    contact_no='+63 2 8123 4567',
                    address='Makati City, Metro Manila'
                ),
                Supplier(
                    name='Honda Parts Philippines',
                    contact_no='+63 2 8765 4321',
                    address='Quezon City, Metro Manila'
                ),
                Supplier(
                    name='Suzuki Motor Philippines',
                    contact_no='+63 2 8234 5678',
                    address='Pasig City, Metro Manila'
                )
            ]
            
            for supplier in suppliers:
                db.session.add(supplier)
            print("Created sample suppliers.")
        
        # Create sample parts
        if Part.query.count() == 0:
            parts = [
                Part(
                    name='Oil Filter',
                    part_type='Engine',
                    brand='Yamaha',
                    price=100.00,
                    stock_quantity=15
                ),
                Part(
                    name='Brake Pads',
                    part_type='Brakes',
                    brand='Honda',
                    price=300.00,
                    stock_quantity=8
                ),
                Part(
                    name='Spark Plug',
                    part_type='Electrical',
                    brand='NGK',
                    price=50.00,
                    stock_quantity=25
                ),
                Part(
                    name='Air Filter',
                    part_type='Engine',
                    brand='Suzuki',
                    price=100.00,
                    stock_quantity=12
                ),
                Part(
                    name='Chain Lubricant',
                    part_type='Body',
                    brand='Motul',
                    price=200.00,
                    stock_quantity=20
                ),
                Part(
                    name='Clutch Cable',
                    part_type='Body',
                    brand='Yamaha',
                    price=150.00,
                    stock_quantity=3  # Low stock item
                ),
                Part(
                    name='Headlight Bulb',
                    part_type='Electrical',
                    brand='Philips',
                    price=80.00,
                    stock_quantity=18
                ),
                Part(
                    name='Rear Tire',
                    part_type='Body',
                    brand='Michelin',
                    price=1200.00,
                    stock_quantity=6
                )
            ]
            
            for part in parts:
                db.session.add(part)
            print("Created sample parts.")
        
        # Create sample staff
        if User.query.count() == 1:  # Only admin exists
            staff = [
                User(
                    username='jsmith',
                    email='john.smith@jrfmotorcycle.com',
                    name='John Smith',
                    role='manager',
                    contact_no='+63 912 345 6789'
                ),
                User(
                    username='sjohnson',
                    email='sarah.johnson@jrfmotorcycle.com',
                    name='Sarah Johnson',
                    role='staff',
                    contact_no='+63 923 456 7890'
                ),
                User(
                    username='mdavis',
                    email='mike.davis@jrfmotorcycle.com',
                    name='Mike Davis',
                    role='staff',
                    contact_no='+63 934 567 8901'
                )
            ]
            
            for user in staff:
                user.set_password('password123')
                db.session.add(user)
            print("Created sample staff.")
        
        # Commit all changes
        db.session.commit()
        
        print("\nDatabase initialization complete!")
        print("================================")
        print("Login Credentials:")
        print("Admin: admin / admin123")
        print("Manager: jsmith / password123")
        print("Staff: sjohnson / password123")
        print("Staff: mdavis / password123")
        print("================================")

if __name__ == '__main__':
    create_tables()
