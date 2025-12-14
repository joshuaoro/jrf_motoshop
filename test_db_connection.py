"""
Database Connection Test Script
This script tests the connection to your database (MySQL or SQLite)
"""
import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_connection():
    """Test database connection and display connection details"""
    print("=" * 60)
    print("DATABASE CONNECTION TEST")
    print("=" * 60)
    print()
    
    # Check for database configuration
    database_url = os.getenv('DATABASE_URL')
    mysql_host = os.getenv('MYSQL_HOST', 'localhost')
    mysql_port = os.getenv('MYSQL_PORT', '3306')
    mysql_user = os.getenv('MYSQL_USER')
    mysql_password = os.getenv('MYSQL_PASSWORD')
    mysql_database = os.getenv('MYSQL_DATABASE')
    
    # Determine which database will be used
    if database_url:
        print(f"✓ DATABASE_URL found: {database_url.split('@')[0]}@***")
        db_type = "MySQL" if "mysql" in database_url.lower() else "SQLite" if "sqlite" in database_url.lower() else "Unknown"
        connection_string = database_url
    elif mysql_user and mysql_password and mysql_database:
        print(f"✓ MySQL environment variables found")
        print(f"  Host: {mysql_host}")
        print(f"  Port: {mysql_port}")
        print(f"  User: {mysql_user}")
        print(f"  Database: {mysql_database}")
        db_type = "MySQL"
        connection_string = f'mysql+pymysql://{mysql_user}:{mysql_password}@{mysql_host}:{mysql_port}/{mysql_database}'
    else:
        print("⚠ No MySQL configuration found")
        print("  Falling back to SQLite (motorshop.db)")
        db_type = "SQLite"
        connection_string = 'sqlite:///motorshop.db'
    
    print()
    print(f"Database Type: {db_type}")
    print()
    
    # Try to import and test connection
    try:
        from flask import Flask
        from flask_sqlalchemy import SQLAlchemy
        
        app = Flask(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = connection_string
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        
        db = SQLAlchemy(app)
        
        print("Attempting to connect to database...")
        print("-" * 60)
        
        with app.app_context():
            # Test basic connection
            try:
                db.engine.connect()
                print("✓ Database connection successful!")
                print()
                
                # Get database info
                if db_type == "MySQL":
                    result = db.session.execute(db.text("SELECT VERSION()"))
                    version = result.scalar()
                    print(f"✓ MySQL Version: {version}")
                    
                    result = db.session.execute(db.text("SELECT DATABASE()"))
                    current_db = result.scalar()
                    print(f"✓ Current Database: {current_db}")
                    
                    result = db.session.execute(db.text("SELECT USER()"))
                    current_user = result.scalar()
                    print(f"✓ Current User: {current_user}")
                else:
                    print(f"✓ SQLite database file: motorshop.db")
                
                print()
                
                # Check if tables exist
                print("Checking database tables...")
                print("-" * 60)
                
                inspector = db.inspect(db.engine)
                tables = inspector.get_table_names()
                
                if tables:
                    print(f"✓ Found {len(tables)} table(s):")
                    for table in sorted(tables):
                        # Get row count
                        try:
                            if db_type == "MySQL":
                                result = db.session.execute(db.text(f"SELECT COUNT(*) FROM `{table}`"))
                            else:
                                result = db.session.execute(db.text(f"SELECT COUNT(*) FROM {table}"))
                            count = result.scalar()
                            print(f"  - {table}: {count} row(s)")
                        except Exception as e:
                            print(f"  - {table}: (unable to count rows)")
                else:
                    print("⚠ No tables found. Run 'python init_db.py' to create tables.")
                
                print()
                print("=" * 60)
                print("✓ CONNECTION TEST PASSED")
                print("=" * 60)
                return True
                
            except Exception as e:
                print(f"✗ Connection failed!")
                print(f"  Error: {str(e)}")
                print()
                print("Troubleshooting:")
                print("  1. Check if MySQL server is running")
                print("  2. Verify database credentials in .env file")
                print("  3. Ensure the database exists")
                print("  4. Check network/firewall settings")
                print()
                print("=" * 60)
                print("✗ CONNECTION TEST FAILED")
                print("=" * 60)
                return False
                
    except ImportError as e:
        print(f"✗ Missing required package: {str(e)}")
        print()
        print("Please install requirements:")
        print("  pip install -r requirements.txt")
        print()
        return False
    except Exception as e:
        print(f"✗ Unexpected error: {str(e)}")
        print()
        return False

if __name__ == '__main__':
    success = test_connection()
    sys.exit(0 if success else 1)


