"""
Quick MySQL Connection Test
This script allows you to test MySQL connection with your credentials
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_mysql_connection():
    """Test MySQL connection with provided credentials"""
    print("=" * 60)
    print("MySQL CONNECTION TEST")
    print("=" * 60)
    print()
    
    # Check if .env file exists
    if not os.path.exists('.env'):
        print("⚠ No .env file found.")
        print()
        print("Please create a .env file with your MySQL credentials:")
        print("-" * 60)
        print("DATABASE_URL=mysql+pymysql://username:password@localhost:3306/database_name")
        print()
        print("OR use individual variables:")
        print("MYSQL_HOST=localhost")
        print("MYSQL_PORT=3306")
        print("MYSQL_USER=your_username")
        print("MYSQL_PASSWORD=your_password")
        print("MYSQL_DATABASE=your_database")
        print("-" * 60)
        print()
        
        # Allow manual input for testing
        print("Would you like to test connection manually? (y/n): ", end='')
        choice = input().strip().lower()
        
        if choice == 'y':
            print()
            host = input("MySQL Host [localhost]: ").strip() or "localhost"
            port = input("MySQL Port [3306]: ").strip() or "3306"
            user = input("MySQL Username: ").strip()
            password = input("MySQL Password: ").strip()
            database = input("MySQL Database: ").strip()
            
            if user and password and database:
                connection_string = f'mysql+pymysql://{user}:{password}@{host}:{port}/{database}'
                test_connection_string(connection_string, host, port, user, database)
            else:
                print("✗ Missing required information")
        return
    
    # Check for existing configuration
    database_url = os.getenv('DATABASE_URL')
    mysql_host = os.getenv('MYSQL_HOST', 'localhost')
    mysql_port = os.getenv('MYSQL_PORT', '3306')
    mysql_user = os.getenv('MYSQL_USER')
    mysql_password = os.getenv('MYSQL_PASSWORD')
    mysql_database = os.getenv('MYSQL_DATABASE')
    
    if database_url and 'mysql' in database_url.lower():
        print(f"✓ Found DATABASE_URL")
        # Extract info for display (hide password)
        if '@' in database_url:
            display_url = database_url.split('@')[0] + '@***'
            print(f"  Connection: {display_url}")
        test_connection_string(database_url, mysql_host, mysql_port, mysql_user or 'user', mysql_database or 'database')
    elif mysql_user and mysql_password and mysql_database:
        print(f"✓ Found MySQL environment variables")
        print(f"  Host: {mysql_host}")
        print(f"  Port: {mysql_port}")
        print(f"  User: {mysql_user}")
        print(f"  Database: {mysql_database}")
        print()
        connection_string = f'mysql+pymysql://{mysql_user}:{mysql_password}@{mysql_host}:{mysql_port}/{mysql_database}'
        test_connection_string(connection_string, mysql_host, mysql_port, mysql_user, mysql_database)
    else:
        print("⚠ No MySQL configuration found in .env file")
        print("  Currently using SQLite fallback")
        print()
        print("To connect to MySQL, add to your .env file:")
        print("-" * 60)
        print("DATABASE_URL=mysql+pymysql://username:password@localhost:3306/database_name")
        print("-" * 60)

def test_connection_string(connection_string, host, port, user, database):
    """Test the actual MySQL connection"""
    try:
        from flask import Flask
        from flask_sqlalchemy import SQLAlchemy
        
        app = Flask(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = connection_string
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        
        db = SQLAlchemy(app)
        
        print()
        print("Testing connection...")
        print("-" * 60)
        
        with app.app_context():
            # Test connection
            conn = db.engine.connect()
            print("✓ Connection established successfully!")
            print()
            
            # Get MySQL version
            result = db.session.execute(db.text("SELECT VERSION()"))
            version = result.scalar()
            print(f"✓ MySQL Server Version: {version}")
            
            # Get current database
            result = db.session.execute(db.text("SELECT DATABASE()"))
            current_db = result.scalar()
            print(f"✓ Connected to Database: {current_db}")
            
            # Get current user
            result = db.session.execute(db.text("SELECT USER()"))
            current_user = result.scalar()
            print(f"✓ Connected as User: {current_user}")
            
            # Check if database exists and get table count
            result = db.session.execute(db.text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE()"))
            table_count = result.scalar()
            print(f"✓ Tables in database: {table_count}")
            
            # List tables if any exist
            if table_count > 0:
                result = db.session.execute(db.text("SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE() ORDER BY table_name"))
                tables = [row[0] for row in result.fetchall()]
                print()
                print("Database tables:")
                for table in tables:
                    # Get row count for each table
                    try:
                        result = db.session.execute(db.text(f"SELECT COUNT(*) FROM `{table}`"))
                        count = result.scalar()
                        print(f"  - {table}: {count} row(s)")
                    except:
                        print(f"  - {table}")
            
            conn.close()
            
            print()
            print("=" * 60)
            print("✓ MySQL CONNECTION TEST PASSED")
            print("=" * 60)
            print()
            print("Your project is successfully connected to MySQL!")
            print("You can now run 'python init_db.py' to create the tables.")
            
    except ImportError as e:
        print(f"✗ Missing package: {str(e)}")
        print("  Run: pip install -r requirements.txt")
    except Exception as e:
        print(f"✗ Connection failed!")
        print(f"  Error: {str(e)}")
        print()
        print("Common issues:")
        print("  1. MySQL server is not running")
        print("  2. Incorrect username or password")
        print("  3. Database does not exist (create it first)")
        print("  4. Host/port is incorrect")
        print("  5. Firewall blocking connection")
        print()
        print("=" * 60)
        print("✗ CONNECTION TEST FAILED")
        print("=" * 60)

if __name__ == '__main__':
    test_mysql_connection()


