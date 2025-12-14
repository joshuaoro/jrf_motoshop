"""
Setup Database Objects Script
This script creates stored procedures, functions, and triggers in MySQL
"""
import os
from dotenv import load_dotenv
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configure database connection
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
        print("Error: MySQL configuration not found in environment variables")
        exit(1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

def setup_database_objects():
    """Read and execute SQL file to create database objects"""
    print("=" * 60)
    print("SETTING UP DATABASE OBJECTS")
    print("=" * 60)
    print()
    
    # Read SQL file
    try:
        with open('database_objects.sql', 'r', encoding='utf-8') as f:
            sql_content = f.read()
    except FileNotFoundError:
        print("✗ Error: database_objects.sql file not found")
        return False
    
    # Split SQL content by delimiter (//)
    # MySQL stored procedures/functions/triggers use DELIMITER //
    statements = []
    current_statement = []
    in_delimiter_block = False
    
    for line in sql_content.split('\n'):
        original_line = line
        line = line.strip()
        
        # Skip empty lines and comments
        if not line or line.startswith('--'):
            continue
        
        # Handle DELIMITER statements
        if line.upper().startswith('DELIMITER'):
            in_delimiter_block = True
            continue
        
        # Check for end of statement (//)
        if line.endswith('//'):
            line = line[:-2].strip()  # Remove //
            if line:
                current_statement.append(line)
            if current_statement:
                statements.append('\n'.join(current_statement))
                current_statement = []
        elif in_delimiter_block:
            current_statement.append(original_line)
    
    # Execute each statement
    with app.app_context():
        connection = db.engine.raw_connection()
        cursor = connection.cursor()
        
        success_count = 0
        error_count = 0
        
        for statement in statements:
            if not statement.strip():
                continue
            
            try:
                # Execute statement
                cursor.execute(statement)
                connection.commit()
                success_count += 1
                
                # Extract object name for display
                if 'CREATE PROCEDURE' in statement.upper():
                    obj_name = statement.split('CREATE PROCEDURE')[1].split('(')[0].strip()
                    print(f"✓ Created stored procedure: {obj_name}")
                elif 'CREATE FUNCTION' in statement.upper():
                    obj_name = statement.split('CREATE FUNCTION')[1].split('(')[0].strip()
                    print(f"✓ Created function: {obj_name}")
                elif 'CREATE TRIGGER' in statement.upper():
                    obj_name = statement.split('CREATE TRIGGER')[1].split()[0].strip()
                    print(f"✓ Created trigger: {obj_name}")
                    
            except Exception as e:
                error_count += 1
                # Check if it's a "already exists" error (which is okay)
                error_msg = str(e).lower()
                if 'already exists' in error_msg or 'duplicate' in error_msg:
                    if 'CREATE PROCEDURE' in statement.upper():
                        obj_name = statement.split('CREATE PROCEDURE')[1].split('(')[0].strip()
                        print(f"⚠ Stored procedure already exists: {obj_name}")
                    elif 'CREATE FUNCTION' in statement.upper():
                        obj_name = statement.split('CREATE FUNCTION')[1].split('(')[0].strip()
                        print(f"⚠ Function already exists: {obj_name}")
                    elif 'CREATE TRIGGER' in statement.upper():
                        obj_name = statement.split('CREATE TRIGGER')[1].split()[0].strip()
                        print(f"⚠ Trigger already exists: {obj_name}")
                else:
                    print(f"✗ Error creating object: {str(e)}")
                    print(f"  Statement: {statement[:100]}...")
        
        cursor.close()
        connection.close()
        
        print()
        print("=" * 60)
        print(f"Setup complete: {success_count} objects created, {error_count} issues")
        print("=" * 60)
        
        return error_count == 0

if __name__ == '__main__':
    success = setup_database_objects()
    if success:
        print("\n✓ All database objects created successfully!")
        print("\nYou can now use:")
        print("  - Stored procedures: GetLowStockParts, CalculateMonthlySales, GetSalesReportByStaff")
        print("  - Functions: CalculateDiscount, GetStockStatus, FormatCurrency")
        print("  - Triggers: trg_update_stock_after_sale, trg_log_stock_entry, trg_prevent_negative_stock")
    else:
        print("\n⚠ Some objects may already exist or there were errors.")
        print("  Check the output above for details.")

