"""
Setup Database Objects Script (PostgreSQL / Supabase)
=====================================================
Creates the helper functions and disables Row Level Security on all app tables
in the cloud Supabase database, using the DATABASE_URL from the .env file.

This is idempotent / safe to run repeatedly. To create the actual TABLES instead,
run the supabase_schema.sql file in the Supabase SQL Editor, or simply run
`python init_db.py` (which creates the tables + seeds data via SQLAlchemy models).
"""

import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()

SCHEMA_FILE = "supabase_functions.sql"


def setup_database_objects():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print(
            "Error: DATABASE_URL not set in .env (Supabase PostgreSQL connection required)."
        )
        return False

    if not os.path.exists(SCHEMA_FILE):
        print(f"Error: {SCHEMA_FILE} not found.")
        return False

    with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
        sql_content = f.read()

    try:
        conn = psycopg2.connect(database_url)
        conn.autocommit = False
        cur = conn.cursor()

        # psycopg2 executes a single multi-statement string in one call.
        cur.execute(sql_content)
        conn.commit()

        cur.close()
        conn.close()
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        print(f"Error applying database objects: {e}")
        return False

    return True


if __name__ == "__main__":
    print("=" * 60)
    print("SETTING UP DATABASE OBJECTS (Supabase PostgreSQL)")
    print("=" * 60)
    ok = setup_database_objects()
    if ok:
        print("OK - Helper functions created and RLS disabled on all app tables.")
        print("  - Functions: GetStockStatus, FormatCurrency, CalculateDiscount")
    else:
        print("FAILED - Setup failed. See error above.")
