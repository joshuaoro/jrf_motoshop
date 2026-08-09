"""
CLI commands for database management.

Run with ``flask --app wsgi <command>``, e.g.::

    flask --app wsgi init-db
    flask --app wsgi create-admin
    flask --app wsgi seed-data
"""

import secrets
import string
import subprocess
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import click
from flask import current_app
from flask.cli import with_appcontext

from app.core.extensions import db
from app.models import Customer, Part, Supplier, User
from app.services.system import SettingsService


def _generate_password(length: int = 16) -> str:
    """Generate a readable but strong random password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


@click.command("init-db")
@click.option(
    "--admin-email",
    default="admin@jrfmotorcycle.com",
    show_default=True,
    help="Email for the bootstrap administrator.",
)
@click.option(
    "--admin-password",
    default=None,
    help="Password for the bootstrap administrator. "
    "A strong one is generated and printed if omitted.",
)
@with_appcontext
def init_db_command(admin_email, admin_password):
    """Create tables, default settings and a bootstrap administrator.

    Prefer `flask db upgrade` for schema changes on an existing deployment;
    this command is for standing up a brand-new database.
    """
    click.echo("Creating database tables...")
    db.create_all()
    click.echo("  tables created.")

    click.echo("Initializing default settings...")
    SettingsService.init_defaults()
    click.echo("  default settings initialized.")

    if User.query.filter_by(email=admin_email).first():
        click.echo(f"Administrator {admin_email} already exists - nothing to do.")
        return

    # Never ship a fixed default credential. The password is either supplied
    # by the operator or randomly generated and shown exactly once.
    generated = admin_password is None
    password = admin_password or _generate_password()

    admin = User(
        name="System Administrator",
        email=admin_email,
        username="admin",
        role="admin",
    )
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()

    click.echo("")
    click.secho("  Administrator account created", fg="green", bold=True)
    click.echo(f"    email:    {admin_email}")
    click.echo("    username: admin")
    if generated:
        click.echo(f"    password: {password}")
        click.secho(
            "    ^ Store this now - it is not recoverable. Change it after " "first login.",
            fg="yellow",
        )
    click.echo("")


@click.command("create-admin")
@click.option("--email", prompt=True, help="Admin email")
@click.option("--username", prompt=True, help="Admin username")
@click.option("--name", prompt=True, help="Admin full name")
@click.option(
    "--password",
    prompt=True,
    hide_input=True,
    confirmation_prompt=True,
    help="Admin password",
)
@with_appcontext
def create_admin_command(email, username, name, password):
    """Create a new admin user"""
    from app.services.users import UserService

    if len(password) < 8:
        click.secho("Error: password must be at least 8 characters", fg="red", err=True)
        raise SystemExit(1)

    try:
        user = UserService.create_user(
            {
                "name": name,
                "email": email,
                "username": username,
                "role": "admin",
                "password": password,
            }
        )
    except ValueError as exc:
        click.secho(f"Error: {exc}", fg="red", err=True)
        raise SystemExit(1)

    click.secho(f"Admin user created: {user.email}", fg="green")


@click.command("seed-data")
@click.option("--force", is_flag=True, help="Seed even if parts already exist")
@with_appcontext
def seed_data_command(force):
    """Seed the database with representative sample data"""
    if Part.query.count() > 0 and not force:
        click.echo("Data already exists. Use --force to seed anyway.")
        return

    click.echo("Seeding sample data...")

    suppliers_data = [
        {
            "name": "Yamaha Motor Philippines",
            "contact_no": "+63 2 8888 9999",
            "email": "parts@yamaha.com.ph",
            "address": "Makati City, Metro Manila",
            "contact_person": "Juan Dela Cruz",
            "payment_terms": "Net 30",
        },
        {
            "name": "Honda Parts Center",
            "contact_no": "+63 2 7777 8888",
            "email": "sales@hondaparts.com.ph",
            "address": "Quezon City, Metro Manila",
            "contact_person": "Maria Santos",
            "payment_terms": "Net 15",
        },
        {
            "name": "Suzuki Accessories Inc.",
            "contact_no": "+63 2 6666 7777",
            "email": "orders@suzuki.com.ph",
            "address": "Pasig City, Metro Manila",
            "contact_person": "Jose Reyes",
            "payment_terms": "COD",
        },
        {
            "name": "Kawasaki Motors Philippines",
            "contact_no": "+63 2 5555 6666",
            "email": "parts@kawasaki.com.ph",
            "address": "Mandaluyong City, Metro Manila",
            "contact_person": "Ana Garcia",
            "payment_terms": "Net 30",
        },
    ]

    for data in suppliers_data:
        if not Supplier.query.filter_by(name=data["name"]).first():
            db.session.add(Supplier(**data))
    db.session.commit()
    click.echo(f"  {len(suppliers_data)} suppliers")

    # cost_price is populated so the profitability report has real margins to
    # work with straight after seeding.
    parts_data = [
        {
            "name": "Engine Oil 10W-40 1L",
            "description": "High-quality 4-stroke engine oil",
            "part_type": "Lubricants",
            "brand": "Yamalube",
            "price": Decimal("350.00"),
            "cost_price": Decimal("245.00"),
            "stock_quantity": 50,
            "min_stock_level": 10,
            "sku": "YAM-OIL-10W40-1L",
            "location": "A1-01",
        },
        {
            "name": "Brake Pads Front (Organic)",
            "description": "Front brake pads for disc brakes",
            "part_type": "Brakes",
            "brand": "Brembo",
            "price": Decimal("1200.00"),
            "cost_price": Decimal("820.00"),
            "stock_quantity": 25,
            "min_stock_level": 5,
            "sku": "BRE-BP-FRONT-ORG",
            "location": "B2-04",
        },
        {
            "name": "Spark Plug CR9E",
            "description": "Standard spark plug for motorcycles",
            "part_type": "Electrical",
            "brand": "NGK",
            "price": Decimal("85.00"),
            "cost_price": Decimal("52.00"),
            "stock_quantity": 100,
            "min_stock_level": 20,
            "sku": "NGK-CR9E",
            "location": "C1-11",
        },
        {
            "name": "Air Filter (High Flow)",
            "description": "High-flow reusable air filter",
            "part_type": "Filters",
            "brand": "K&N",
            "price": Decimal("650.00"),
            "cost_price": Decimal("430.00"),
            "stock_quantity": 30,
            "min_stock_level": 8,
            "sku": "KN-AF-HIGH",
            "location": "A3-07",
        },
        {
            "name": "Drive Chain 520-120",
            "description": "Heavy-duty drive chain",
            "part_type": "Transmission",
            "brand": "RK",
            "price": Decimal("800.00"),
            "cost_price": Decimal("560.00"),
            "stock_quantity": 15,
            "min_stock_level": 3,
            "sku": "RK-CH-520-120",
            "location": "D1-02",
        },
        {
            "name": "Clutch Cable",
            "description": "Universal clutch cable",
            "part_type": "Transmission",
            "brand": "Yamaha",
            "price": Decimal("280.00"),
            "cost_price": Decimal("175.00"),
            "stock_quantity": 40,
            "min_stock_level": 10,
            "sku": "YAM-CC-UNIV",
            "location": "D1-05",
        },
        {
            "name": "Radiator Hose Set",
            "description": "Complete radiator hose kit",
            "part_type": "Cooling",
            "brand": "Honda",
            "price": Decimal("320.00"),
            "cost_price": Decimal("205.00"),
            "stock_quantity": 20,
            "min_stock_level": 5,
            "sku": "HON-RH-SET",
            "location": "E2-01",
        },
        {
            "name": "Turn Signal LED",
            "description": "LED turn signal lights (pair)",
            "part_type": "Electrical",
            "brand": "Suzuki",
            "price": Decimal("150.00"),
            "cost_price": Decimal("88.00"),
            "stock_quantity": 60,
            "min_stock_level": 15,
            "sku": "SUZ-TS-LED",
            "location": "C2-03",
        },
        {
            "name": "Foot Peg Set",
            "description": "Adjustable foot pegs",
            "part_type": "Body",
            "brand": "Kawasaki",
            "price": Decimal("180.00"),
            "cost_price": Decimal("112.00"),
            "stock_quantity": 35,
            "min_stock_level": 7,
            "sku": "KAW-FP-ADJ",
            "location": "F1-09",
        },
        {
            "name": "Motorcycle Battery 12V 8Ah",
            "description": "Maintenance-free battery",
            "part_type": "Electrical",
            "brand": "Motobatt",
            "price": Decimal("1500.00"),
            "cost_price": Decimal("1080.00"),
            "stock_quantity": 2,
            "min_stock_level": 5,
            "sku": "MOT-BAT-12V-8AH",
            "location": "C3-01",
        },
    ]

    for data in parts_data:
        if not Part.query.filter_by(sku=data["sku"]).first():
            db.session.add(Part(**data))
    db.session.commit()
    click.echo(f"  {len(parts_data)} parts")

    customers_data = [
        {
            "name": "Juan Dela Cruz",
            "email": "juan@email.com",
            "phone": "+63 912 345 6789",
            "address": "123 Manila St.",
            "city": "Manila",
            "postal_code": "1000",
        },
        {
            "name": "Maria Santos",
            "email": "maria@email.com",
            "phone": "+63 923 456 7890",
            "address": "456 Quezon Ave.",
            "city": "Quezon City",
            "postal_code": "1100",
        },
        {
            "name": "Jose Reyes",
            "email": "jose@email.com",
            "phone": "+63 934 567 8901",
            "address": "789 Makati Ave.",
            "city": "Makati",
            "postal_code": "1200",
        },
        {
            "name": "Ana Garcia",
            "email": "ana@email.com",
            "phone": "+63 945 678 9012",
            "address": "321 Pasig Blvd.",
            "city": "Pasig",
            "postal_code": "1600",
        },
        {
            "name": "Pedro Martinez",
            "email": "pedro@email.com",
            "phone": "+63 956 789 0123",
            "address": "654 Mandaluyong Rd.",
            "city": "Mandaluyong",
            "postal_code": "1550",
        },
    ]

    for data in customers_data:
        if not Customer.query.filter_by(email=data["email"]).first():
            db.session.add(Customer(**data))
    db.session.commit()
    click.echo(f"  {len(customers_data)} customers")

    click.secho("Sample data seeded successfully.", fg="green")


@click.command("backup-db")
@click.option("--output", "-o", help="Output file path")
@with_appcontext
def backup_db_command(output):
    """Create a database backup using pg_dump"""
    db_url = current_app.config["SQLALCHEMY_DATABASE_URI"]
    if not db_url.startswith("postgresql"):
        click.secho("backup-db requires a PostgreSQL database.", fg="red", err=True)
        raise SystemExit(1)

    if output:
        target = Path(output)
    else:
        backup_dir = Path(
            SettingsService.get_setting("backup", "backup_location")
            or current_app.config.get("BACKUP_DIR", "./backups")
        )
        target = backup_dir / f"jrf_backup_{datetime.utcnow():%Y%m%d_%H%M%S}.sql"

    target.parent.mkdir(parents=True, exist_ok=True)
    click.echo(f"Creating backup: {target}")

    try:
        result = subprocess.run(
            ["pg_dump", db_url, "--no-owner", "--no-privileges", "--file", str(target)],
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    except FileNotFoundError:
        click.secho(
            "pg_dump not found on PATH. Install the PostgreSQL client tools.",
            fg="red",
            err=True,
        )
        raise SystemExit(1)

    if result.returncode != 0:
        click.secho(f"Backup failed: {result.stderr.strip()}", fg="red", err=True)
        raise SystemExit(1)

    click.secho(f"Backup created: {target} ({target.stat().st_size:,} bytes)", fg="green")


@click.command("cleanup")
@click.option("--days", default=90, show_default=True, help="Days of system logs to keep")
@click.option("--dry-run", is_flag=True, help="Report what would be deleted")
@with_appcontext
def cleanup_command(days, dry_run):
    """Clean up old logs and read notifications"""
    from app.models import AuditLog, Notification, SystemLog

    now = datetime.utcnow()
    cutoff = now - timedelta(days=days)
    click.echo(f"Cleaning data older than {days} days (cutoff: {cutoff.date()})")

    targets = (
        ("system logs", SystemLog.query.filter(SystemLog.log_date < cutoff)),
        (
            "audit logs",
            AuditLog.query.filter(AuditLog.action_date < now - timedelta(days=max(days, 365))),
        ),
        (
            "read notifications",
            Notification.query.filter(
                Notification.is_read.is_(True),
                Notification.read_at < now - timedelta(days=30),
            ),
        ),
    )

    for label, query in targets:
        if dry_run:
            click.echo(f"  would delete {query.count()} {label}")
        else:
            click.echo(f"  deleted {query.delete(synchronize_session=False)} {label}")

    if dry_run:
        db.session.rollback()
        click.echo("Dry run - nothing was deleted.")
    else:
        db.session.commit()
        click.secho("Cleanup completed.", fg="green")


@click.command("reindex")
@with_appcontext
def reindex_command():
    """Rebuild database indexes (PostgreSQL only)"""
    from sqlalchemy import text

    if db.engine.name != "postgresql":
        click.secho(
            f"reindex is PostgreSQL-only (current: {db.engine.name}).",
            fg="yellow",
            err=True,
        )
        raise SystemExit(1)

    # REINDEX DATABASE needs a literal database name - CURRENT_DATABASE() is
    # a function call and is not accepted there. Look the name up first.
    #
    # REINDEX cannot run inside a transaction block, so use an AUTOCOMMIT
    # connection rather than the ORM session.
    with db.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        database = conn.execute(text("SELECT current_database()")).scalar()
        click.echo(f'Rebuilding indexes for "{database}"...')
        try:
            conn.execute(text(f'REINDEX DATABASE "{database}"'))
        except Exception as exc:
            click.secho(f"Reindex failed: {exc}", fg="red", err=True)
            raise SystemExit(1)

    click.secho("Indexes rebuilt successfully.", fg="green")
