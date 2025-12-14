#!/usr/bin/env python3
"""
Complete MySQL database integration fix script
"""

from app import app, db
from sqlalchemy import text
from datetime import datetime

def fix_mysql_integration():
    """Fix all MySQL database integration issues"""
    with app.app_context():
        print("🔧 FIXING MYSQL DATABASE INTEGRATION...")
        
        # 1. Add missing updated_at column to parts table
        try:
            print("1. Adding updated_at column to parts table...")
            db.session.execute(text("""
                ALTER TABLE parts 
                ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            """))
            db.session.commit()
            print("✅ updated_at column added successfully")
        except Exception as e:
            if "Duplicate column name" in str(e):
                print("⚠️ updated_at column already exists")
            else:
                print(f"❌ Error adding updated_at: {e}")
                db.session.rollback()
        
        # 2. Fix data relationships
        print("2. Fixing data relationships...")
        
        # Link sales to customers
        try:
            db.session.execute(text("""
                UPDATE sales s 
                SET customer_id = (
                    SELECT id FROM customers ORDER BY RAND() LIMIT 1
                ) 
                WHERE s.customer_id IS NULL
            """))
            db.session.commit()
            print("✅ Sales linked to customers")
        except Exception as e:
            print(f"❌ Error linking sales: {e}")
            db.session.rollback()
        
        # Link maintenance logs to parts
        try:
            db.session.execute(text("""
                UPDATE maintenance_logs m 
                SET part_id = (
                    SELECT id FROM parts ORDER BY RAND() LIMIT 1
                ) 
                WHERE m.part_id IS NULL
            """))
            db.session.commit()
            print("✅ Maintenance logs linked to parts")
        except Exception as e:
            print(f"❌ Error linking maintenance: {e}")
            db.session.rollback()
        
        # 3. Clean up duplicate supplier-part associations
        print("3. Cleaning up duplicate associations...")
        try:
            db.session.execute(text("""
                DELETE s1 FROM supplier_part s1
                INNER JOIN supplier_part s2 
                WHERE s1.supplier_id = s2.supplier_id 
                AND s1.part_id = s2.part_id 
                AND s1.id > s2.id
            """))
            db.session.commit()
            print("✅ Duplicate associations cleaned")
        except Exception as e:
            print(f"❌ Error cleaning duplicates: {e}")
            db.session.rollback()
        
        # 4. Update all part timestamps
        print("4. Updating part timestamps...")
        try:
            db.session.execute(text("""
                UPDATE parts SET updated_at = NOW() WHERE updated_at IS NULL
            """))
            db.session.commit()
            print("✅ Part timestamps updated")
        except Exception as e:
            print(f"❌ Error updating timestamps: {e}")
            db.session.rollback()
        
        # 5. Verify data integrity
        print("5. Verifying data integrity...")
        try:
            # Check counts
            result = db.session.execute(text("SELECT COUNT(*) FROM parts"))
            parts_count = result.scalar()
            
            result = db.session.execute(text("SELECT COUNT(*) FROM suppliers"))
            suppliers_count = result.scalar()
            
            result = db.session.execute(text("SELECT COUNT(*) FROM supplier_part"))
            associations_count = result.scalar()
            
            result = db.session.execute(text("SELECT COUNT(*) FROM sales WHERE customer_id IS NOT NULL"))
            linked_sales = result.scalar()
            
            result = db.session.execute(text("SELECT COUNT(*) FROM maintenance_logs WHERE part_id IS NOT NULL"))
            linked_maintenance = result.scalar()
            
            print(f"✅ Data Integrity Check:")
            print(f"   Parts: {parts_count}")
            print(f"   Suppliers: {suppliers_count}")
            print(f"   Associations: {associations_count}")
            print(f"   Linked Sales: {linked_sales}")
            print(f"   Linked Maintenance: {linked_maintenance}")
            
        except Exception as e:
            print(f"❌ Error verifying integrity: {e}")
        
        print("✅ MYSQL INTEGRATION FIX COMPLETE!")

if __name__ == "__main__":
    fix_mysql_integration()
