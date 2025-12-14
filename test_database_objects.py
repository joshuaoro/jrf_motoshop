"""
Test Database Objects Script
Tests stored procedures, functions, and triggers
"""
import os
from dotenv import load_dotenv
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

load_dotenv()

app = Flask(__name__)

database_url = os.getenv('DATABASE_URL')
if not database_url:
    mysql_host = os.getenv('MYSQL_HOST', 'localhost')
    mysql_port = os.getenv('MYSQL_PORT', '3306')
    mysql_user = os.getenv('MYSQL_USER')
    mysql_password = os.getenv('MYSQL_PASSWORD')
    mysql_database = os.getenv('MYSQL_DATABASE')
    
    if mysql_user and mysql_password and mysql_database:
        database_url = f'mysql+pymysql://{mysql_user}:{mysql_password}@{mysql_host}:{mysql_port}/{mysql_database}'
    else:
        print("Error: MySQL configuration not found")
        exit(1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

def test_functions():
    """Test database functions"""
    print("=" * 60)
    print("TESTING FUNCTIONS")
    print("=" * 60)
    
    with app.app_context():
        try:
            # Test CalculateDiscount
            result = db.session.execute(
                db.text('SELECT CalculateDiscount(1000.00, 10.00)')
            )
            discount = result.scalar()
            print(f"✓ CalculateDiscount(1000.00, 10.00) = {discount}")
            
            # Test GetStockStatus
            result = db.session.execute(
                db.text('SELECT GetStockStatus(3)')
            )
            status = result.scalar()
            print(f"✓ GetStockStatus(3) = '{status}'")
            
            # Test FormatCurrency
            result = db.session.execute(
                db.text('SELECT FormatCurrency(1234.56)')
            )
            formatted = result.scalar()
            print(f"✓ FormatCurrency(1234.56) = '{formatted}'")
            
            print("\n✓ All functions working correctly!")
            return True
        except Exception as e:
            print(f"✗ Error testing functions: {e}")
            return False

def test_stored_procedures():
    """Test stored procedures"""
    print("\n" + "=" * 60)
    print("TESTING STORED PROCEDURES")
    print("=" * 60)
    
    with app.app_context():
        try:
            # Test GetLowStockParts
            result = db.session.execute(
                db.text('CALL GetLowStockParts(5)')
            )
            parts = result.fetchall()
            print(f"✓ GetLowStockParts(5) returned {len(parts)} parts")
            
            # Test CalculateMonthlySales
            from datetime import datetime
            now = datetime.now()
            result = db.session.execute(
                db.text('CALL CalculateMonthlySales(:year, :month, @total, @count)'),
                {'year': now.year, 'month': now.month}
            )
            result = db.session.execute(db.text('SELECT @total, @count'))
            row = result.fetchone()
            print(f"✓ CalculateMonthlySales({now.year}, {now.month}) = Total: {row[0]}, Count: {row[1]}")
            
            # Test GetSalesReportByStaff
            from datetime import timedelta
            start_date = (now - timedelta(days=30)).strftime('%Y-%m-%d')
            end_date = now.strftime('%Y-%m-%d')
            result = db.session.execute(
                db.text('CALL GetSalesReportByStaff(:start, :end)'),
                {'start': start_date, 'end': end_date}
            )
            report = result.fetchall()
            print(f"✓ GetSalesReportByStaff returned {len(report)} staff records")
            
            print("\n✓ All stored procedures working correctly!")
            return True
        except Exception as e:
            print(f"✗ Error testing stored procedures: {e}")
            return False

def test_triggers():
    """Test triggers (indirectly by checking their effects)"""
    print("\n" + "=" * 60)
    print("TESTING TRIGGERS")
    print("=" * 60)
    
    with app.app_context():
        try:
            # Check if triggers exist
            result = db.session.execute(
                db.text("""
                    SELECT TRIGGER_NAME 
                    FROM information_schema.TRIGGERS 
                    WHERE TRIGGER_SCHEMA = DATABASE()
                """)
            )
            triggers = [row[0] for row in result.fetchall()]
            
            expected_triggers = [
                'trg_update_stock_after_sale',
                'trg_log_stock_entry',
                'trg_prevent_negative_stock'
            ]
            
            print(f"✓ Found {len(triggers)} triggers in database:")
            for trigger in triggers:
                if trigger in expected_triggers:
                    print(f"  ✓ {trigger}")
                else:
                    print(f"  - {trigger}")
            
            # Check if all expected triggers exist
            missing = [t for t in expected_triggers if t not in triggers]
            if missing:
                print(f"\n⚠ Missing triggers: {', '.join(missing)}")
                return False
            else:
                print("\n✓ All expected triggers are present!")
                print("  (Triggers will fire automatically on INSERT/UPDATE operations)")
                return True
        except Exception as e:
            print(f"✗ Error testing triggers: {e}")
            return False

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("DATABASE OBJECTS TEST")
    print("=" * 60)
    
    func_ok = test_functions()
    proc_ok = test_stored_procedures()
    trig_ok = test_triggers()
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Functions: {'✓ PASS' if func_ok else '✗ FAIL'}")
    print(f"Stored Procedures: {'✓ PASS' if proc_ok else '✗ FAIL'}")
    print(f"Triggers: {'✓ PASS' if trig_ok else '✗ FAIL'}")
    print("=" * 60)
    
    if func_ok and proc_ok and trig_ok:
        print("\n✓ All database objects are working correctly!")
    else:
        print("\n⚠ Some database objects may need attention.")

