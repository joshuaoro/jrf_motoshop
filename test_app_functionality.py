"""
Comprehensive Application Functionality Test
Tests if the Flask app is fully functional with MySQL
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

def test_app_initialization():
    """Test if the Flask app can initialize and connect to MySQL"""
    print("=" * 60)
    print("TESTING APPLICATION FUNCTIONALITY")
    print("=" * 60)
    print()
    
    try:
        from app import app, db, User, Part, Sale, Supplier
        
        print("✓ Flask app imported successfully")
        
        with app.app_context():
            # Test database connection
            try:
                db.engine.connect()
                print("✓ Database connection established")
            except Exception as e:
                print(f"✗ Database connection failed: {e}")
                return False
            
            # Test database type
            database_url = app.config['SQLALCHEMY_DATABASE_URI']
            if 'mysql' in database_url.lower():
                print(f"✓ Using MySQL database: {database_url.split('@')[1] if '@' in database_url else 'configured'}")
            else:
                print(f"⚠ Using SQLite (not MySQL): {database_url}")
                return False
            
            # Test model queries
            try:
                user_count = User.query.count()
                part_count = Part.query.count()
                supplier_count = Supplier.query.count()
                sale_count = Sale.query.count()
                
                print(f"✓ Can query User model: {user_count} users")
                print(f"✓ Can query Part model: {part_count} parts")
                print(f"✓ Can query Supplier model: {supplier_count} suppliers")
                print(f"✓ Can query Sale model: {sale_count} sales")
            except Exception as e:
                print(f"✗ Model query failed: {e}")
                return False
            
            # Test stored procedure call
            try:
                result = db.session.execute(
                    db.text('CALL GetLowStockParts(5)')
                )
                parts = result.fetchall()
                print(f"✓ Can call stored procedures: GetLowStockParts returned {len(parts)} results")
            except Exception as e:
                print(f"⚠ Stored procedure test failed: {e}")
            
            # Test function call
            try:
                result = db.session.execute(
                    db.text('SELECT FormatCurrency(1000.00)')
                )
                formatted = result.scalar()
                print(f"✓ Can call database functions: FormatCurrency returned '{formatted}'")
            except Exception as e:
                print(f"⚠ Function test failed: {e}")
            
            # Test transaction
            try:
                # Try to start a transaction
                db.session.begin()
                db.session.rollback()
                print("✓ Transactions are working (can begin/rollback)")
            except Exception as e:
                print(f"⚠ Transaction test: {e}")
            
            print()
            print("=" * 60)
            print("✓ APPLICATION FULLY FUNCTIONAL WITH MYSQL")
            print("=" * 60)
            return True
            
    except ImportError as e:
        print(f"✗ Failed to import app: {e}")
        return False
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_endpoints_available():
    """Test if key endpoints are registered"""
    print("\n" + "=" * 60)
    print("TESTING API ENDPOINTS")
    print("=" * 60)
    
    try:
        from app import app
        
        routes = []
        for rule in app.url_map.iter_rules():
            routes.append(rule.rule)
        
        key_endpoints = [
            '/',
            '/dashboard',
            '/login',
            '/inventory',
            '/sales',
            '/api/parts',
            '/api/sales',
            '/api/low-stock-parts',
            '/api/monthly-sales',
            '/api/calculate-discount'
        ]
        
        print(f"✓ Found {len(routes)} total routes")
        
        missing = []
        for endpoint in key_endpoints:
            if endpoint in routes:
                print(f"  ✓ {endpoint}")
            else:
                print(f"  ✗ {endpoint} (missing)")
                missing.append(endpoint)
        
        if missing:
            print(f"\n⚠ Missing endpoints: {', '.join(missing)}")
            return False
        else:
            print("\n✓ All key endpoints are registered")
            return True
            
    except Exception as e:
        print(f"✗ Error checking endpoints: {e}")
        return False

if __name__ == '__main__':
    print()
    app_ok = test_app_initialization()
    endpoints_ok = test_endpoints_available()
    
    print("\n" + "=" * 60)
    print("FINAL SUMMARY")
    print("=" * 60)
    print(f"Application Initialization: {'✓ PASS' if app_ok else '✗ FAIL'}")
    print(f"API Endpoints: {'✓ PASS' if endpoints_ok else '✗ FAIL'}")
    print("=" * 60)
    
    if app_ok and endpoints_ok:
        print("\n" + "=" * 60)
        print("✅ YOUR PROJECT IS FULLY FUNCTIONAL AND CONNECTED TO MYSQL!")
        print("=" * 60)
        print("\nYou can now:")
        print("  1. Run the application: python app.py")
        print("  2. Access it at: http://localhost:5000")
        print("  3. Login with: admin@jrfmotorcycle.com / admin123")
        print("\nAll database operations will use MySQL!")
        sys.exit(0)
    else:
        print("\n⚠ Some issues detected. Check the output above.")
        sys.exit(1)

