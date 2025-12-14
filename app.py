from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from functools import wraps
import os
from dotenv import load_dotenv
from sqlalchemy import text, func

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-123')

# MySQL connection configuration - REQUIRED
# Connection string format: mysql+pymysql://username:password@host:port/database_name
database_url = os.getenv('DATABASE_URL')

if not database_url:
    # Build connection string from individual MySQL environment variables
    mysql_host = os.getenv('MYSQL_HOST', 'localhost')
    mysql_port = os.getenv('MYSQL_PORT', '3306')
    mysql_user = os.getenv('MYSQL_USER')
    mysql_password = os.getenv('MYSQL_PASSWORD')
    mysql_database = os.getenv('MYSQL_DATABASE')
    
    if mysql_user and mysql_password and mysql_database:
        database_url = f'mysql+pymysql://{mysql_user}:{mysql_password}@{mysql_host}:{mysql_port}/{mysql_database}'
    else:
        # MySQL connection is REQUIRED - no fallback to SQLite
        raise ValueError(
            "MySQL database connection is required. Please set either:\n"
            "  - DATABASE_URL environment variable, OR\n"
            "  - MYSQL_USER, MYSQL_PASSWORD, and MYSQL_DATABASE environment variables\n"
            "Example: DATABASE_URL=mysql+pymysql://user:pass@localhost:3306/jrf_motorshop"
        )

# Validate that we're using MySQL (not SQLite)
if not database_url.startswith('mysql'):
    raise ValueError(
        f"Invalid database connection. MySQL is required, but got: {database_url.split('://')[0]}\n"
        "Please configure MySQL connection in your .env file."
    )

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Custom filter for time ago
@app.template_filter('time_ago')
def time_ago(timestamp):
    if not timestamp:
        return "Never"
    
    now = datetime.utcnow()
    if isinstance(timestamp, str):
        timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    
    diff = now - timestamp
    seconds = diff.total_seconds()
    
    if seconds < 60:
        return "Just now"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    else:
        days = int(seconds / 86400)
        return f"{days} day{'s' if days != 1 else ''} ago"

@app.template_filter('escapejs')
def escapejs(value):
    """Escape JavaScript strings in templates"""
    import html
    return html.escape(str(value)).replace('\\', '\\\\').replace("'", "\\'").replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')

# Models
class User(UserMixin, db.Model):
    __tablename__ = 'staff'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(50), nullable=False)
    contact_no = db.Column(db.String(20))
    email = db.Column(db.String(100), unique=True, nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    
    sales = db.relationship('Sale', backref='staff', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    # Role-based access control methods
    def is_admin(self):
        """Check if user has admin role"""
        return self.role == 'admin'
    
    def is_manager(self):
        """Check if user has manager role"""
        return self.role == 'manager'
    
    def is_staff(self):
        """Check if user has staff role"""
        return self.role == 'staff'
    
    def has_role(self, *roles):
        """Check if user has any of the specified roles"""
        return self.role in roles
    
    def can_manage_staff(self):
        """Only admin can manage staff"""
        return self.is_admin()
    
    def can_manage_inventory(self):
        """Admin and manager can manage inventory"""
        return self.is_admin() or self.is_manager()
    
    def can_view_reports(self):
        """Admin and manager can view reports"""
        return self.is_admin() or self.is_manager()
    
    def can_manage_suppliers(self):
        """Admin and manager can manage suppliers"""
        return self.is_admin() or self.is_manager()

class Settings(db.Model):
    __tablename__ = 'settings'
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(50), nullable=False)  # general, inventory, sales, notifications, backup, security
    setting_key = db.Column(db.String(100), nullable=False)
    setting_value = db.Column(db.Text)
    setting_type = db.Column(db.String(20), default='string')  # string, number, boolean, json
    description = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey('staff.id'))
    
    # Unique constraint on category and key
    __table_args__ = (db.UniqueConstraint('category', 'setting_key'),)
    
    def __repr__(self):
        return f'<Settings {self.category}.{self.setting_key}={self.setting_value}>'

class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('staff.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(50), default='info')  # info, warning, error, success
    category = db.Column(db.String(50), default='system')  # system, inventory, sales, staff, backup
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read_at = db.Column(db.DateTime)
    action_url = db.Column(db.String(500))  # Optional URL to redirect when clicked
    action_text = db.Column(db.String(100))  # Optional button text
    
    # Relationships
    user = db.relationship('User', backref=db.backref('notifications', lazy=True, cascade='all, delete-orphan'))
    
    def __repr__(self):
        return f'<Notification {self.title} for {self.user.name}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'message': self.message,
            'type': self.type,
            'category': self.category,
            'is_read': self.is_read,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'read_at': self.read_at.isoformat() if self.read_at else None,
            'action_url': self.action_url,
            'action_text': self.action_text,
            'time_ago': time_ago(self.created_at)
        }

# Default settings initialization
def init_default_settings():
    """Initialize default settings if they don't exist"""
    default_settings = {
        'general': {
            'store_name': 'JRF Motorcycle Parts & Accessories',
            'store_address': '123 Main Street, Manila, Philippines',
            'contact_number': '+63 2 1234 5678',
            'email_address': 'info@jrfmotorparts.com',
            'currency': 'PHP',
            'timezone': 'Asia/Manila'
        },
        'inventory': {
            'low_stock_alert': 'true',
            'low_stock_threshold': '5',
            'auto_generate_sku': 'true',
            'track_serial_numbers': 'false'
        },
        'sales': {
            'tax_rate': '0.12',
            'default_payment_method': 'cash',
            'enable_receipts': 'true',
            'email_receipts': 'false',
            'receipt_header': 'JRF MOTORCYCLE PARTS',
            'receipt_footer': 'Thank you for your business!'
        },
        'notifications': {
            'email_notifications': 'true',
            'low_stock_email': 'true',
            'sales_email': 'false',
            'backup_reminder': 'true',
            'notification_email': 'admin@jrfmotorparts.com'
        },
        'backup': {
            'auto_backup': 'true',
            'backup_frequency': 'daily',
            'backup_retention': '30',
            'backup_location': './backups'
        },
        'security': {
            'session_timeout': '30',
            'password_min_length': '8',
            'require_password_change': 'false',
            'login_attempts': '3'
        }
    }
    
    for category, settings in default_settings.items():
        for key, value in settings.items():
            existing = Settings.query.filter_by(category=category, setting_key=key).first()
            if not existing:
                setting = Settings(
                    category=category,
                    setting_key=key,
                    setting_value=value,
                    setting_type='string' if value not in ['true', 'false'] else 'boolean',
                    description=f"Default {key.replace('_', ' ').title()} setting"
                )
                db.session.add(setting)
    
    db.session.commit()

# Notification helper functions
def create_notification(user_id, title, message, type='info', category='system', action_url=None, action_text=None):
    """Create a new notification for a user"""
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        type=type,
        category=category,
        action_url=action_url,
        action_text=action_text
    )
    db.session.add(notification)
    db.session.commit()
    return notification

def create_notification_for_role(role, title, message, type='info', category='system', action_url=None, action_text=None):
    """Create notifications for all users with a specific role"""
    users = User.query.filter_by(role=role).all()
    notifications = []
    for user in users:
        notification = create_notification(user.id, title, message, type, category, action_url, action_text)
        notifications.append(notification)
    return notifications

def create_notification_for_all(title, message, type='info', category='system', action_url=None, action_text=None):
    """Create notifications for all users"""
    users = User.query.all()
    notifications = []
    for user in users:
        notification = create_notification(user.id, title, message, type, category, action_url, action_text)
        notifications.append(notification)
    return notifications

def mark_notification_read(notification_id, user_id):
    """Mark a notification as read"""
    notification = Notification.query.filter_by(id=notification_id, user_id=user_id).first()
    if notification and not notification.is_read:
        notification.is_read = True
        notification.read_at = datetime.utcnow()
        db.session.commit()
        return True
    return False

def mark_all_notifications_read(user_id):
    """Mark all notifications as read for a user"""
    notifications = Notification.query.filter_by(user_id=user_id, is_read=False).all()
    for notification in notifications:
        notification.is_read = True
        notification.read_at = datetime.utcnow()
    db.session.commit()
    return len(notifications)

def get_unread_count(user_id):
    """Get count of unread notifications for a user"""
    return Notification.query.filter_by(user_id=user_id, is_read=False).count()

def get_recent_notifications(user_id, limit=10):
    """Get recent notifications for a user"""
    return Notification.query.filter_by(user_id=user_id).order_by(Notification.created_at.desc()).limit(limit).all()

# Auto-create notifications for system events
def check_low_stock_alerts():
    """Check for low stock items and create notifications"""
    threshold_setting = Settings.query.filter_by(category='inventory', setting_key='low_stock_threshold').first()
    enabled_setting = Settings.query.filter_by(category='inventory', setting_key='low_stock_alert').first()
    
    if not enabled_setting or enabled_setting.setting_value != 'true':
        return
    
    threshold = int(threshold_setting.setting_value) if threshold_setting else 5
    low_stock_parts = Part.query.filter(Part.stock_quantity < threshold).all()
    
    if low_stock_parts:
        title = f"Low Stock Alert - {len(low_stock_parts)} items"
        message = f"The following parts are running low on stock: {', '.join([part.name for part in low_stock_parts[:5]])}"
        if len(low_stock_parts) > 5:
            message += f" and {len(low_stock_parts) - 5} more"
        
        create_notification_for_role('admin', title, message, 'warning', 'inventory', '/inventory', 'View Inventory')
        create_notification_for_role('manager', title, message, 'warning', 'inventory', '/inventory', 'View Inventory')

class Part(db.Model):
    __tablename__ = 'parts'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    part_type = db.Column(db.String(50))
    brand = db.Column(db.String(50))
    price = db.Column(db.Float, nullable=False)
    stock_quantity = db.Column(db.Integer, default=0)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    stock_entries = db.relationship('StockEntry', backref='part', lazy=True)
    sale_details = db.relationship('SaleDetail', backref='part', lazy=True)
    suppliers = db.relationship('Supplier', secondary='supplier_part', back_populates='parts')

class Supplier(db.Model):
    __tablename__ = 'suppliers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    contact_no = db.Column(db.String(20))
    address = db.Column(db.Text)
    
    parts = db.relationship('Part', secondary='supplier_part', back_populates='suppliers')

class StockEntry(db.Model):
    __tablename__ = 'stock_entries'
    id = db.Column(db.Integer, primary_key=True)
    entry_date = db.Column(db.DateTime, default=datetime.utcnow)
    quantity = db.Column(db.Integer, nullable=False)
    part_id = db.Column(db.Integer, db.ForeignKey('parts.id'), nullable=False)

class Sale(db.Model):
    __tablename__ = 'sales'
    id = db.Column(db.Integer, primary_key=True)
    sale_date = db.Column(db.DateTime, default=datetime.utcnow)
    total_amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(50), nullable=False)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id'), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'))
    receipt_number = db.Column(db.String(50), unique=True)
    notes = db.Column(db.Text)
    
    details = db.relationship('SaleDetail', backref='sale', lazy=True, cascade='all, delete-orphan')

class SaleDetail(db.Model):
    __tablename__ = 'sale_details'
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), primary_key=True)
    part_id = db.Column(db.Integer, db.ForeignKey('parts.id'), primary_key=True)
    quantity = db.Column(db.Integer, nullable=False)
    price_at_sale = db.Column(db.Float, nullable=False)

# Association table for many-to-many relationship between Supplier and Part
supplier_part = db.Table('supplier_part',
    db.Column('supplier_id', db.Integer, db.ForeignKey('suppliers.id'), primary_key=True),
    db.Column('part_id', db.Integer, db.ForeignKey('parts.id'), primary_key=True)
)

# Additional models for complete database integration
class BackupLog(db.Model):
    __tablename__ = 'backup_logs'
    id = db.Column(db.Integer, primary_key=True)
    backup_date = db.Column(db.DateTime, default=datetime.utcnow)
    backup_type = db.Column(db.String(50), default='manual')  # manual, auto
    backup_location = db.Column(db.String(500))
    file_size = db.Column(db.BigInteger)
    status = db.Column(db.String(20), default='success')  # success, failed, in_progress
    created_by = db.Column(db.Integer, db.ForeignKey('staff.id'))
    
    creator = db.relationship('User', backref='backups')

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    action_date = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('staff.id'))
    action_type = db.Column(db.String(50), nullable=False)  # create, update, delete, login, logout
    table_name = db.Column(db.String(50), nullable=False)
    record_id = db.Column(db.Integer)
    old_values = db.Column(db.Text)  # JSON string
    new_values = db.Column(db.Text)  # JSON string
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(500))
    
    user = db.relationship('User', backref='audit_logs')

class SystemLog(db.Model):
    __tablename__ = 'system_logs'
    id = db.Column(db.Integer, primary_key=True)
    log_date = db.Column(db.DateTime, default=datetime.utcnow)
    log_level = db.Column(db.String(20), default='info')  # info, warning, error, critical
    category = db.Column(db.String(50))  # system, database, security, performance
    message = db.Column(db.Text, nullable=False)
    details = db.Column(db.Text)  # JSON string for additional details
    source = db.Column(db.String(100))  # module or component that generated the log

class Customer(db.Model):
    __tablename__ = 'customers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True)
    phone = db.Column(db.String(20))
    address = db.Column(db.Text)
    created_date = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    sales = db.relationship('Sale', backref='customer', lazy=True)

class PurchaseOrder(db.Model):
    __tablename__ = 'purchase_orders'
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(50), unique=True, nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False)
    order_date = db.Column(db.DateTime, default=datetime.utcnow)
    expected_date = db.Column(db.DateTime)
    status = db.Column(db.String(50), default='pending')  # pending, ordered, received, cancelled
    total_amount = db.Column(db.Float, default=0.0)
    created_by = db.Column(db.Integer, db.ForeignKey('staff.id'))
    
    supplier = db.relationship('Supplier', backref='purchase_orders')
    creator = db.relationship('User', backref='purchase_orders')
    items = db.relationship('PurchaseOrderItem', backref='purchase_order', lazy=True, cascade='all, delete-orphan')

class PurchaseOrderItem(db.Model):
    __tablename__ = 'purchase_order_items'
    id = db.Column(db.Integer, primary_key=True)
    purchase_order_id = db.Column(db.Integer, db.ForeignKey('purchase_orders.id'), nullable=False)
    part_id = db.Column(db.Integer, db.ForeignKey('parts.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    
    part = db.relationship('Part', backref='purchase_items')

class Expense(db.Model):
    __tablename__ = 'expenses'
    id = db.Column(db.Integer, primary_key=True)
    expense_date = db.Column(db.DateTime, default=datetime.utcnow)
    category = db.Column(db.String(50), nullable=False)  # rent, utilities, supplies, maintenance, other
    description = db.Column(db.Text, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(50), nullable=False)
    receipt_number = db.Column(db.String(100))
    created_by = db.Column(db.Integer, db.ForeignKey('staff.id'))
    
    creator = db.relationship('User', backref='expenses')

class MaintenanceLog(db.Model):
    __tablename__ = 'maintenance_logs'
    id = db.Column(db.Integer, primary_key=True)
    part_id = db.Column(db.Integer, db.ForeignKey('parts.id'), nullable=True)  # Link to parts for inventory maintenance
    maintenance_date = db.Column(db.DateTime, default=datetime.utcnow)
    maintenance_type = db.Column(db.String(50), nullable=False)  # preventive, corrective, emergency
    equipment_name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    cost = db.Column(db.Float, default=0.0)
    performed_by = db.Column(db.String(100))  # external technician or internal staff
    notes = db.Column(db.Text)  # Additional notes
    next_maintenance = db.Column(db.DateTime)
    created_by = db.Column(db.Integer, db.ForeignKey('staff.id'))
    
    creator = db.relationship('User', backref='maintenance_logs')
    part = db.relationship('Part', backref='maintenance_logs')

# Audit and System Logging Functions
def log_audit(action_type, table_name, record_id=None, old_values=None, new_values=None, user_id=None):
    """Create an audit log entry"""
    import json
    from flask import request
    
    audit = AuditLog(
        user_id=user_id or (current_user.id if current_user.is_authenticated else None),
        action_type=action_type,
        table_name=table_name,
        record_id=record_id,
        old_values=json.dumps(old_values) if old_values else None,
        new_values=json.dumps(new_values) if new_values else None,
        ip_address=request.remote_addr if request else None,
        user_agent=request.headers.get('User-Agent') if request else None
    )
    db.session.add(audit)
    db.session.commit()

def log_system(level, message, category='system', details=None, source='application'):
    """Create a system log entry"""
    import json
    
    log = SystemLog(
        log_level=level,
        message=message,
        category=category,
        details=json.dumps(details) if details else None,
        source=source
    )
    db.session.add(log)
    db.session.commit()

def generate_receipt_number():
    """Generate unique receipt number"""
    import uuid
    return f"RCP-{datetime.utcnow().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

def generate_purchase_order_number():
    """Generate unique purchase order number"""
    import uuid
    return f"PO-{datetime.utcnow().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

# Database initialization helper
def init_database_data():
    """Initialize database with default data"""
    try:
        # Create tables
        db.create_all()
        
        # Initialize settings
        init_default_settings()
        
        # Create default admin user if not exists
        admin_user = User.query.filter_by(email='admin@jrfmotorcycle.com').first()
        if not admin_user:
            admin_user = User(
                name='System Administrator',
                email='admin@jrfmotorcycle.com',
                username='admin',
                role='admin',
                contact_no='+63 2 1234 5678'
            )
            admin_user.set_password('admin123')
            db.session.add(admin_user)
            db.session.commit()
            log_system('info', 'Default admin user created', 'system', {'username': 'admin'})
        
        # Create sample data if tables are empty
        if Part.query.count() == 0:
            create_sample_data()
        
        log_system('info', 'Database initialization completed', 'system')
        
    except Exception as e:
        log_system('error', f'Database initialization failed: {str(e)}', 'system')
        raise

def create_sample_data():
    """Create sample data for testing"""
    import json
    
    # Sample parts
    parts_data = [
        {
            'name': 'Engine Oil - 4T',
            'description': 'High-quality 4-stroke engine oil',
            'part_type': 'Lubricants',
            'brand': 'Shell',
            'price': 250.00,
            'stock_quantity': 50
        },
        {
            'name': 'Spark Plug - NGK',
            'description': 'Standard spark plug for motorcycles',
            'part_type': 'Ignition',
            'brand': 'NGK',
            'price': 85.00,
            'stock_quantity': 100
        },
        {
            'name': 'Brake Pads - Front',
            'description': 'Front brake pads for disk brakes',
            'part_type': 'Brakes',
            'brand': 'Brembo',
            'price': 450.00,
            'stock_quantity': 30
        },
        {
            'name': 'Air Filter',
            'description': 'Reusable air filter',
            'part_type': 'Filters',
            'brand': 'K&N',
            'price': 650.00,
            'stock_quantity': 25
        },
        {
            'name': 'Chain Lubricant',
            'description': 'High-performance chain lubricant',
            'part_type': 'Lubricants',
            'brand': 'Motul',
            'price': 180.00,
            'stock_quantity': 75
        }
    ]
    
    for part_data in parts_data:
        part = Part(**part_data)
        db.session.add(part)
    
    # Sample suppliers
    suppliers_data = [
        {
            'name': 'Auto Parts Philippines',
            'contact_no': '+63 2 8888 9999',
            'address': '123 Makati Avenue, Makati City'
        },
        {
            'name': 'Motorcycle Supply Co.',
            'contact_no': '+63 2 7777 6666',
            'address': '456 Quezon Avenue, Quezon City'
        }
    ]
    
    for supplier_data in suppliers_data:
        supplier = Supplier(**supplier_data)
        db.session.add(supplier)
    
    # Sample customers
    customers_data = [
        {
            'name': 'Juan Santos',
            'email': 'juan.santos@email.com',
            'phone': '+63 912 345 6789',
            'address': '789 Manila Street, Manila'
        },
        {
            'name': 'Maria Reyes',
            'email': 'maria.reyes@email.com',
            'phone': '+63 923 456 7890',
            'address': '321 Cebu Road, Cebu City'
        }
    ]
    
    for customer_data in customers_data:
        customer = Customer(**customer_data)
        db.session.add(customer)
    
    db.session.commit()
    log_system('info', 'Sample data created', 'system', {
        'parts': len(parts_data),
        'suppliers': len(suppliers_data),
        'customers': len(customers_data)
    })

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Context processor to make role checks available in all templates
@app.context_processor
def inject_user_permissions():
    """Inject user permissions and notification data into all templates"""
    if current_user.is_authenticated:
        unread_count = get_unread_count(current_user.id)
        recent_notifications = get_recent_notifications(current_user.id, limit=5)

        return {
            'is_admin': current_user.is_admin(),
            'is_manager': current_user.is_manager(),
            'is_staff': current_user.is_staff(),
            'can_manage_inventory': current_user.can_manage_inventory(),
            'can_manage_staff': current_user.can_manage_staff(),
            'can_view_reports': current_user.can_view_reports(),
            'can_manage_suppliers': current_user.can_manage_suppliers(),
            'unread_notifications': unread_count,
            'recent_notifications': [n.to_dict() for n in recent_notifications]
        }
    return {
        'is_admin': False,
        'is_manager': False,
        'is_staff': False,
        'can_manage_inventory': False,
        'can_manage_staff': False,
        'can_view_reports': False,
        'can_manage_suppliers': False,
        'unread_notifications': 0,
        'recent_notifications': []
    }

# Role-based access control decorators
def role_required(*roles):
    """
    Decorator to restrict access to routes based on user roles.
    Usage: @role_required('admin', 'manager')
    """
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if not current_user.has_role(*roles):
                flash('You do not have permission to access this page.', 'error')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def admin_required(f):
    """Decorator to restrict access to admin only"""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin():
            flash('Admin access required.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def manager_required(f):
    """Decorator to restrict access to manager and admin"""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        if not (current_user.is_admin() or current_user.is_manager()):
            flash('Manager access required.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
@app.route('/dashboard')
@login_required
def dashboard():
    # Get real-time statistics
    stats = get_realtime_stats()
    
    # Get real-time activities
    activities = get_realtime_activities()
    
    # Log dashboard access
    log_audit('login', 'dashboard', user_id=current_user.id)
    
    return render_template('dashboard.html', 
                         recent_activities=activities,
                         total_parts=stats['total_parts'],
                         low_stock_parts=stats['low_stock_parts'],
                         total_sales=stats['total_sales'],
                         total_suppliers=stats['total_suppliers'],
                         total_customers=stats['total_customers'],
                         today_revenue=stats['today_revenue'])

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        flash('Invalid email or password', 'error')
    
    # Create admin user if not exists
    if not User.query.filter_by(email='admin@jrfmotorcycle.com').first():
        admin = User(
            name='Admin User',
            email='admin@jrfmotorcycle.com',
            username='admin',
            role='admin',
            password_hash=generate_password_hash('admin123')
        )
        db.session.add(admin)
        db.session.commit()
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/inventory')
@login_required
def inventory():
    # All authenticated users can view inventory
    # But only admin/manager can edit (handled in template)
    parts = Part.query.all()
    parts_json = [{
        'id': part.id,
        'part_id': part.id,
        'name': part.name,
        'part_type': part.part_type,
        'type': part.part_type,  # Add alias for compatibility
        'brand': part.brand,
        'price': float(part.price),
        'stock_quantity': part.stock_quantity,
        'stock': part.stock_quantity,  # Add alias for compatibility
        'description': part.description or '',
        'suppliers': [{
            'id': supplier.id,
            'name': supplier.name
        } for supplier in part.suppliers]
    } for part in parts]
    return render_template('inventory.html', parts=parts, parts_json=parts_json)

@app.route('/suppliers')
@login_required
def suppliers():
    # Get all suppliers from database
    suppliers = Supplier.query.all()
    
    suppliers_data = []
    for supplier in suppliers:
        parts_count = len(supplier.parts) if supplier.parts else 0
        
        supplier_data = {
            'id': supplier.id,
            'name': supplier.name,
            'contact_no': supplier.contact_no or '',
            'email': '',  # No email field in Supplier model
            'phone': supplier.contact_no or '',
            'address': supplier.address or '',
            'created_date': '',  # No created_date field in Supplier model
            'parts_count': parts_count,
            'total_purchase_orders': len(supplier.purchase_orders) if hasattr(supplier, 'purchase_orders') and supplier.purchase_orders else 0
        }
        
        suppliers_data.append(supplier_data)
    
    return render_template('suppliers.html', suppliers=suppliers_data, suppliers_json=suppliers_data)

@app.route('/api/create-supplier-associations', methods=['POST'])
@login_required
def create_supplier_associations():
    """Force create supplier-part associations for testing"""
    try:
        suppliers = Supplier.query.all()
        parts = Part.query.all()
        
        if not suppliers or not parts:
            return jsonify({'success': False, 'message': 'No suppliers or parts found'})
        
        # Clear existing associations
        from sqlalchemy import text
        db.session.execute(text("DELETE FROM supplier_part"))
        db.session.commit()
        
        # Create new associations
        associations_created = 0
        for i, supplier in enumerate(suppliers[:3]):  # First 3 suppliers
            for j, part in enumerate(parts[i*2:(i+1)*2]):  # 2 parts each
                if part and supplier:
                    supplier.parts.append(part)
                    associations_created += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'Created {associations_created} supplier-part associations',
            'associations': associations_created
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/api/debug-suppliers-parts', methods=['GET'])
@login_required
def debug_suppliers_parts():
    """Debug endpoint to check suppliers and parts in database"""
    try:
        suppliers = Supplier.query.all()
        parts = Part.query.all()
        
        supplier_info = []
        for supplier in suppliers:
            supplier_info.append({
                'id': supplier.id,
                'name': supplier.name,
                'parts_count': len(supplier.parts) if supplier.parts else 0,
                'parts': [p.name for p in supplier.parts] if supplier.parts else []
            })
        
        part_info = []
        for part in parts:
            part_info.append({
                'id': part.id,
                'name': part.name,
                'suppliers_count': len(part.suppliers) if part.suppliers else 0,
                'suppliers': [s.name for s in part.suppliers] if part.suppliers else []
            })
        
        # Check association table
        from sqlalchemy import text
        association_count = db.session.execute(text("SELECT COUNT(*) FROM supplier_part")).scalar()
        
        return jsonify({
            'suppliers_count': len(suppliers),
            'parts_count': len(parts),
            'association_count': association_count,
            'suppliers': supplier_info,
            'parts': part_info
        })
        
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/test-supplier-data')
@login_required
def test_supplier_data():
    """Test endpoint to show raw supplier data"""
    try:
        suppliers = Supplier.query.all()
        parts = Part.query.all()
        
        # Check association table
        from sqlalchemy import text
        association_count = db.session.execute(text("SELECT COUNT(*) FROM supplier_part")).scalar()
        
        # Get detailed association data
        associations = db.session.execute(text("""
            SELECT s.name as supplier_name, p.name as part_name 
            FROM supplier_part sp 
            JOIN suppliers s ON sp.supplier_id = s.id 
            JOIN parts p ON sp.part_id = p.id
        """)).fetchall()
        
        return jsonify({
            'suppliers_count': len(suppliers),
            'parts_count': len(parts),
            'association_count': association_count,
            'associations': [{'supplier': row[0], 'part': row[1]} for row in associations]
        })
        
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/sales')
@login_required
def sales():
    parts = Part.query.all()
    parts_data = []
    parts_json = []
    
    for part in parts:
        part_dict = {
            'part_id': part.id,
            'name': part.name,
            'part_type': part.part_type,
            'brand': part.brand,
            'price': part.price,
            'stock_quantity': part.stock_quantity,
            'description': part.description,
            'suppliers': [{'id': supplier.id, 'name': supplier.name} for supplier in part.suppliers]
        }
        parts_data.append(part_dict)
        parts_json.append(part_dict)
    
    customers = Customer.query.filter_by(is_active=True).all()
    customers_data = [{
        'id': customer.id,
        'name': customer.name,
        'email': customer.email,
        'phone': customer.phone,
        'address': customer.address
    } for customer in customers]
    
    return render_template('sales.html', parts=parts_data, parts_json=parts_json, customers=customers_data)

@app.route('/customers')
@login_required
def customers():
    # Get all active customers from database
    customers = Customer.query.filter_by(is_active=True).all()
    customers_data = [{
        'id': customer.id,
        'name': customer.name,
        'email': customer.email,
        'phone': customer.phone,
        'address': customer.address,
        'created_date': customer.created_date.strftime('%Y-%m-%d') if customer.created_date else '',
        'total_sales': len(customer.sales) if customer.sales else 0,
        'total_spent': sum(sale.total_amount for sale in customer.sales) if customer.sales else 0
    } for customer in customers]
    
    return render_template('customers.html', customers=customers_data, customers_json=customers_data)

@app.route('/staff')
@admin_required
def staff():
    staff = User.query.all()
    staff_json = [{
        'id': user.id,
        'name': user.name,
        'email': user.email,
        'username': user.username,
        'role': user.role,
        'contact_no': user.contact_no,
        'sales_count': len(user.sales)
    } for user in staff]
    return render_template('staff.html', staff=staff, staff_json=staff_json)

@app.route('/reports')
@manager_required
def reports():
    # Get low stock threshold from settings
    threshold_setting = Settings.query.filter_by(category='inventory', setting_key='low_stock_threshold').first()
    low_stock_threshold = int(threshold_setting.setting_value) if threshold_setting else 5
    
    # Get store settings
    store_name_setting = Settings.query.filter_by(category='general', setting_key='store_name').first()
    currency_setting = Settings.query.filter_by(category='general', setting_key='currency').first()
    
    store_name = store_name_setting.setting_value if store_name_setting else 'JRF Motorshop'
    currency = currency_setting.setting_value if currency_setting else 'PHP'
    currency_symbol = '₱' if currency == 'PHP' else '$' if currency == 'USD' else '€'
    
    # Get statistics from database
    total_parts = Part.query.count()
    low_stock_parts = Part.query.filter(Part.stock_quantity < low_stock_threshold).count()
    total_sales = Sale.query.count()
    total_suppliers = Supplier.query.count()
    
    # Get recent activities from database
    recent_sales = Sale.query.order_by(Sale.sale_date.desc()).limit(3).all()
    recent_activities = []
    
    for sale in recent_sales:
        recent_activities.append({
            'message': f"New sale: {currency_symbol}{sale.total_amount:.2f}",
            'timestamp': sale.sale_date,
            'icon': 'fas fa-shopping-cart',
            'icon_bg': 'bg-green-500'
        })
    
    # Add low stock alerts
    low_stock_parts_list = Part.query.filter(Part.stock_quantity < low_stock_threshold).limit(3).all()
    for part in low_stock_parts_list:
        recent_activities.append({
            'message': f"Low stock alert: {part.name} ({part.stock_quantity} left)",
            'timestamp': datetime.utcnow(),
            'icon': 'fas fa-exclamation-triangle',
            'icon_bg': 'bg-yellow-500'
        })
    
    return render_template('reports.html', 
                         recent_activities=recent_activities[:5],
                         total_parts=total_parts,
                         low_stock_parts=low_stock_parts,
                         total_sales=total_sales,
                         total_suppliers=total_suppliers,
                         store_name=store_name,
                         currency_symbol=currency_symbol)

@app.route('/settings')
@manager_required
def settings():
    # Only admin and manager can access settings
    # Initialize default settings if needed (only if no settings exist at all)
    if Settings.query.count() == 0:
        init_default_settings()
    
    # Get all settings grouped by category
    all_settings = Settings.query.order_by(Settings.category, Settings.setting_key).all()
    settings_dict = {}
    for setting in all_settings:
        if setting.category not in settings_dict:
            settings_dict[setting.category] = {}
        settings_dict[setting.category][setting.setting_key] = {
            'value': setting.setting_value,
            'type': setting.setting_type,
            'description': setting.description
        }
    
    last_backup = BackupLog.query.order_by(BackupLog.backup_date.desc()).first()
    if last_backup:
        last_backup_display = last_backup.backup_date.strftime('%B %d, %Y at %I:%M %p')
    else:
        last_backup_display = 'No backups yet'
    
    return render_template('settings.html', settings=settings_dict, last_backup=last_backup_display)

@app.route('/notifications')
@login_required
def notifications():
    """Notifications page with real-time data"""
    # Get user's notifications from database
    user_notifications = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(50).all()
    
    notifications_data = [{
        'id': notification.id,
        'title': notification.title,
        'message': notification.message,
        'type': notification.type,
        'is_read': notification.is_read,
        'created_at': notification.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        'read_at': notification.read_at.strftime('%Y-%m-%d %H:%M:%S') if notification.read_at else None,
        'action_url': notification.action_url,
        'action_text': notification.action_text
    } for notification in user_notifications]
    
    # Get unread count
    unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    
    return render_template('notifications.html', notifications=notifications_data, unread_count=unread_count)

# Settings API Routes
@app.route('/api/settings', methods=['GET', 'POST', 'PUT'])
@manager_required
def api_settings():
    if request.method == 'GET':
        # Get all settings
        all_settings = Settings.query.order_by(Settings.category, Settings.setting_key).all()
        settings_dict = {}
        for setting in all_settings:
            if setting.category not in settings_dict:
                settings_dict[setting.category] = {}
            settings_dict[setting.category][setting.setting_key] = {
                'value': setting.setting_value,
                'type': setting.setting_type,
                'description': setting.description
            }
        return jsonify(settings_dict)
    
    elif request.method in ['POST', 'PUT']:
        # Update settings
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        try:
            for category, settings in data.items():
                for key, value in settings.items():
                    setting = Settings.query.filter_by(category=category, setting_key=key).first()
                    if setting:
                        # Convert boolean values
                        if setting.setting_type == 'boolean':
                            setting.setting_value = 'true' if str(value).lower() in ['true', '1', 'on'] else 'false'
                        else:
                            setting.setting_value = str(value)
                        setting.updated_by = current_user.id
                        setting.updated_at = datetime.utcnow()
                    else:
                        # Create new setting if it doesn't exist
                        setting_type = 'boolean' if str(value).lower() in ['true', 'false'] else 'string'
                        setting = Settings(
                            category=category,
                            setting_key=key,
                            setting_value=str(value),
                            setting_type=setting_type,
                            updated_by=current_user.id
                        )
                        db.session.add(setting)
            
            db.session.commit()
            return jsonify({'success': True, 'message': 'Settings updated successfully'})
        
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': f'Failed to update settings: {str(e)}'}), 500

@app.route('/api/settings/sales/tax_rate', methods=['GET'])
def get_tax_rate():
    """Get tax rate - public endpoint for sales page"""
    setting = Settings.query.filter_by(category='sales', setting_key='tax_rate').first()
    if setting:
        return jsonify({
            'category': setting.category,
            'key': setting.setting_key,
            'value': setting.setting_value,
            'type': setting.setting_type,
            'description': setting.description
        })
    else:
        # Return default tax rate if not found
        return jsonify({
            'category': 'sales',
            'key': 'tax_rate',
            'value': '12',
            'type': 'number',
            'description': 'Default tax rate'
        })

@app.route('/api/settings/<category>/<key>', methods=['GET', 'PUT', 'DELETE'])
@manager_required
def api_setting_detail(category, key):
    setting = Settings.query.filter_by(category=category, setting_key=key).first()
    
    if request.method == 'GET':
        if not setting:
            return jsonify({'error': 'Setting not found'}), 404
        return jsonify({
            'category': setting.category,
            'key': setting.setting_key,
            'value': setting.setting_value,
            'type': setting.setting_type,
            'description': setting.description
        })
    
    elif request.method == 'PUT':
        if not setting:
            return jsonify({'error': 'Setting not found'}), 404
        
        data = request.get_json()
        if not data or 'value' not in data:
            return jsonify({'error': 'No value provided'}), 400
        
        try:
            setting.setting_value = str(data['value'])
            if setting.setting_type == 'boolean':
                setting.setting_value = 'true' if str(data['value']).lower() in ['true', '1', 'on'] else 'false'
            setting.updated_by = current_user.id
            setting.updated_at = datetime.utcnow()
            db.session.commit()
            return jsonify({'success': True, 'message': 'Setting updated successfully'})
        
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': f'Failed to update setting: {str(e)}'}), 500
    
    elif request.method == 'DELETE':
        if not setting:
            return jsonify({'error': 'Setting not found'}), 404
        
        try:
            db.session.delete(setting)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Setting deleted successfully'})
        
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': f'Failed to delete setting: {str(e)}'}), 500

@app.route('/api/settings/export')
@manager_required
def export_settings():
    """Export all settings as JSON"""
    all_settings = Settings.query.order_by(Settings.category, Settings.setting_key).all()
    settings_dict = {}
    for setting in all_settings:
        if setting.category not in settings_dict:
            settings_dict[setting.category] = {}
        settings_dict[setting.category][setting.setting_key] = {
            'value': setting.setting_value,
            'type': setting.setting_type,
            'description': setting.description
        }
    
    return jsonify({
        'exported_at': datetime.utcnow().isoformat(),
        'exported_by': current_user.name,
        'settings': settings_dict
    })

@app.route('/api/settings/import', methods=['POST'])
@manager_required
def import_settings():
    """Import settings from JSON"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not file.filename.endswith('.json'):
        return jsonify({'error': 'File must be a JSON file'}), 400
    
    try:
        import json
        data = json.loads(file.read().decode('utf-8'))
        
        if 'settings' not in data:
            return jsonify({'error': 'Invalid settings file format'}), 400
        
        # Import settings
        for category, settings in data['settings'].items():
            for key, setting_data in settings.items():
                setting = Settings.query.filter_by(category=category, setting_key=key).first()
                if setting:
                    setting.setting_value = str(setting_data.get('value', ''))
                    setting.setting_type = setting_data.get('type', 'string')
                    setting.description = setting_data.get('description', '')
                    setting.updated_by = current_user.id
                    setting.updated_at = datetime.utcnow()
                else:
                    setting = Settings(
                        category=category,
                        setting_key=key,
                        setting_value=str(setting_data.get('value', '')),
                        setting_type=setting_data.get('type', 'string'),
                        description=setting_data.get('description', ''),
                        updated_by=current_user.id
                    )
                    db.session.add(setting)
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'Settings imported successfully'})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to import settings: {str(e)}'}), 500

@app.route('/api/settings/reset', methods=['POST'])
@manager_required
def reset_settings_api():
    """Reset all settings to their default values"""
    try:
        # Remove all existing settings
        Settings.query.delete()
        db.session.commit()

        # Re-initialize default settings
        init_default_settings()

        return jsonify({'success': True, 'message': 'Settings reset to defaults'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to reset settings: {str(e)}'}), 500

# Notification API Routes
@app.route('/api/notifications', methods=['GET'])
@login_required
def get_notifications():
    """Get user's notifications"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    unread_only = request.args.get('unread_only', 'false').lower() == 'true'
    
    query = Notification.query.filter_by(user_id=current_user.id)
    
    if unread_only:
        query = query.filter_by(is_read=False)
    
    notifications = query.order_by(Notification.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return jsonify({
        'notifications': [n.to_dict() for n in notifications.items],
        'total': notifications.total,
        'pages': notifications.pages,
        'current_page': page,
        'unread_count': get_unread_count(current_user.id)
    })

@app.route('/api/notifications/unread-count', methods=['GET'])
@login_required
def get_unread_notifications_count():
    """Get count of unread notifications"""
    return jsonify({
        'unread_count': get_unread_count(current_user.id)
    })

@app.route('/api/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
def mark_notification_as_read(notification_id):
    """Mark a notification as read"""
    success = mark_notification_read(notification_id, current_user.id)
    if success:
        return jsonify({
            'success': True,
            'unread_count': get_unread_count(current_user.id)
        })
    else:
        return jsonify({'error': 'Notification not found or already read'}), 404

@app.route('/api/notifications/mark-all-read', methods=['POST'])
@login_required
def mark_all_notifications_as_read():
    """Mark all notifications as read"""
    count = mark_all_notifications_read(current_user.id)
    return jsonify({
        'success': True,
        'marked_count': count,
        'unread_count': 0
    })

@app.route('/api/notifications/<int:notification_id>', methods=['DELETE'])
@login_required
def delete_notification(notification_id):
    """Delete a notification"""
    notification = Notification.query.filter_by(id=notification_id, user_id=current_user.id).first()
    if notification:
        db.session.delete(notification)
        db.session.commit()
        return jsonify({
            'success': True,
            'unread_count': get_unread_count(current_user.id)
        })
    else:
        return jsonify({'error': 'Notification not found'}), 404

@app.route('/api/notifications/clear-all', methods=['DELETE'])
@login_required
def clear_all_notifications():
    """Clear all notifications for user"""
    Notification.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return jsonify({
        'success': True,
        'cleared_count': Notification.query.filter_by(user_id=current_user.id).count()
    })

@app.route('/api/notifications/test', methods=['POST'])
@login_required
def create_test_notification():
    """Create a test notification (for testing purposes)"""
    if not current_user.is_admin():
        return jsonify({'error': 'Admin access required'}), 403
    
    data = request.get_json()
    title = data.get('title', 'Test Notification')
    message = data.get('message', 'This is a test notification')
    notification_type = data.get('type', 'info')
    
    notification = create_notification(
        current_user.id,
        title,
        message,
        notification_type,
        'system'
    )
    
    return jsonify({
        'success': True,
        'notification': notification.to_dict()
    })

# Real-time data refresh utilities
def get_realtime_stats():
    """Get real-time statistics for dashboard"""
    # Get low stock threshold from settings
    threshold_setting = Settings.query.filter_by(category='inventory', setting_key='low_stock_threshold').first()
    low_stock_threshold = int(threshold_setting.setting_value) if threshold_setting else 5
    
    # Calculate real-time stats
    total_parts = Part.query.count()
    low_stock_parts = Part.query.filter(Part.stock_quantity < low_stock_threshold).count()
    total_sales = Sale.query.count()
    total_suppliers = Supplier.query.count()
    total_customers = Customer.query.filter_by(is_active=True).count()
    total_staff = User.query.count()
    
    # Recent sales (last 24 hours)
    from datetime import datetime, timedelta
    yesterday = datetime.utcnow() - timedelta(days=1)
    recent_sales = Sale.query.filter(Sale.sale_date >= yesterday).count()
    
    # Today's revenue
    today = datetime.utcnow().date()
    start_of_day = datetime.combine(today, datetime.min.time())
    today_revenue = db.session.query(db.func.sum(Sale.total_amount)).filter(Sale.sale_date >= start_of_day).scalar() or 0
    
    return {
        'total_parts': total_parts,
        'low_stock_parts': low_stock_parts,
        'total_sales': total_sales,
        'total_suppliers': total_suppliers,
        'total_customers': total_customers,
        'total_staff': total_staff,
        'recent_sales': recent_sales,
        'today_revenue': float(today_revenue),
        'timestamp': datetime.utcnow().isoformat()
    }

def get_realtime_activities():
    """Get real-time activities for dashboard"""
    activities = []
    
    # Recent sales (last 5)
    recent_sales = Sale.query.order_by(Sale.sale_date.desc()).limit(5).all()
    for sale in recent_sales:
        activities.append({
            'type': 'sale',
            'message': f"New sale: ₱{sale.total_amount:.2f}",
            'timestamp': sale.sale_date.isoformat(),
            'icon': 'fas fa-shopping-cart',
            'icon_bg': 'bg-green-500'
        })
    
    # Low stock alerts
    threshold_setting = Settings.query.filter_by(category='inventory', setting_key='low_stock_threshold').first()
    low_stock_threshold = int(threshold_setting.setting_value) if threshold_setting else 5
    low_stock_parts = Part.query.filter(Part.stock_quantity < low_stock_threshold).limit(3).all()
    
    for part in low_stock_parts:
        activities.append({
            'type': 'low_stock',
            'message': f"Low stock alert: {part.name} ({part.stock_quantity} left)",
            'timestamp': datetime.utcnow().isoformat(),
            'icon': 'fas fa-exclamation-triangle',
            'icon_bg': 'bg-yellow-500'
        })
    
    # Sort by timestamp
    activities.sort(key=lambda x: x['timestamp'], reverse=True)
    return activities[:10]

# Real-time API endpoints
@app.route('/api/realtime/stats', methods=['GET'])
@login_required
def get_realtime_stats_api():
    """Get real-time statistics"""
    return jsonify(get_realtime_stats())

@app.route('/api/realtime/activities', methods=['GET'])
@login_required
def get_realtime_activities_api():
    """Get real-time activities"""
    return jsonify(get_realtime_activities())

@app.route('/api/realtime/inventory', methods=['GET'])
@login_required
def get_realtime_inventory():
    """Get real-time inventory data"""
    parts = Part.query.order_by(Part.updated_at.desc()).limit(20).all()
    return jsonify([{
        'id': part.id,
        'name': part.name,
        'part_type': part.part_type,
        'brand': part.brand,
        'price': float(part.price),
        'stock_quantity': part.stock_quantity,
        'description': part.description or '',
        'updated_at': part.updated_at.isoformat() if part.updated_at else None
    } for part in parts])

@app.route('/api/realtime/sales', methods=['GET'])
@login_required
def get_realtime_sales():
    """Get real-time sales data"""
    recent_sales = db.session.query(Sale, Customer).join(Customer, Sale.customer_id == Customer.id, isouter=True).order_by(Sale.sale_date.desc()).limit(10).all()
    return jsonify([{
        'id': sale.id,
        'total_amount': float(sale.total_amount),
        'payment_method': sale.payment_method,
        'created_at': sale.sale_date.isoformat(),
        'staff_name': sale.staff.name if sale.staff else 'Unknown',
        'customer_name': customer.name if customer else 'Walk-in Customer',
        'customer_email': customer.email if customer else None
    } for sale, customer in recent_sales])

@app.route('/api/realtime/notifications', methods=['GET'])
@login_required
def get_realtime_notifications():
    """Get real-time notifications"""
    notifications = Notification.query.filter_by(user_id=current_user.id, is_read=False).order_by(Notification.created_at.desc()).limit(10).all()
    return jsonify([{
        'id': notification.id,
        'title': notification.title,
        'message': notification.message,
        'type': notification.type,
        'created_at': notification.created_at.isoformat(),
        'action_url': notification.action_url
    } for notification in notifications])

@app.route('/api/realtime/customers', methods=['GET'])
@login_required
def get_realtime_customers():
    """Get real-time customers data"""
    recent_customers = Customer.query.filter_by(is_active=True).order_by(Customer.created_date.desc()).limit(10).all()
    return jsonify([{
        'id': customer.id,
        'name': customer.name,
        'email': customer.email,
        'phone': customer.phone,
        'total_sales': len(customer.sales) if customer.sales else 0,
        'total_spent': sum(sale.total_amount for sale in customer.sales) if customer.sales else 0,
        'created_at': customer.created_date.isoformat() if customer.created_date else None
    } for customer in recent_customers])

# Comprehensive API Routes for Complete Database Integration

# Customers API
@app.route('/api/customers', methods=['GET', 'POST'])
@login_required
def api_customers():
    if request.method == 'GET':
        customers = Customer.query.filter_by(is_active=True).all()
        return jsonify([{
            'id': customer.id,
            'name': customer.name,
            'email': customer.email,
            'phone': customer.phone,
            'address': customer.address,
            'created_date': customer.created_date.isoformat()
        } for customer in customers])
    
    elif request.method == 'POST':
        if not current_user.can_manage_inventory():
            return jsonify({'error': 'Insufficient permissions'}), 403
        
        data = request.get_json()
        
        # Check if email already exists
        if Customer.query.filter_by(email=data['email']).first():
            return jsonify({'error': 'Email already exists'}), 400
        
        customer = Customer(
            name=data['name'],
            email=data['email'],
            phone=data.get('phone', ''),
            address=data.get('address', '')
        )
        
        db.session.add(customer)
        db.session.commit()
        
        log_audit('create', 'customers', customer.id, None, data, current_user.id)
        create_notification(current_user.id, 'New Customer Added', f'Customer {customer.name} has been added to the system.', 'success', 'sales')
        
        return jsonify({
            'success': True,
            'customer': {
                'id': customer.id,
                'name': customer.name,
                'email': customer.email,
                'phone': customer.phone,
                'address': customer.address,
                'created_date': customer.created_date.isoformat()
            }
        })

@app.route('/api/customers/<int:customer_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def api_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    
    if request.method == 'GET':
        return jsonify({
            'id': customer.id,
            'name': customer.name,
            'email': customer.email,
            'phone': customer.phone,
            'address': customer.address,
            'created_date': customer.created_date.isoformat()
        })
    
    elif request.method == 'PUT':
        if not current_user.can_manage_inventory():
            return jsonify({'error': 'Insufficient permissions'}), 403
        
        old_data = {
            'name': customer.name,
            'email': customer.email,
            'phone': customer.phone,
            'address': customer.address
        }
        
        data = request.get_json()
        customer.name = data['name']
        customer.email = data['email']
        customer.phone = data.get('phone', customer.phone)
        customer.address = data.get('address', customer.address)
        
        db.session.commit()
        
        log_audit('update', 'customers', customer.id, old_data, data, current_user.id)
        
        return jsonify({'success': True})
    
    elif request.method == 'DELETE':
        if not current_user.can_manage_inventory():
            return jsonify({'error': 'Insufficient permissions'}), 403
        
        customer.is_active = False
        db.session.commit()
        
        log_audit('delete', 'customers', customer.id, {'name': customer.name}, None, current_user.id)
        
        return jsonify({'success': True})

# Suppliers API
@app.route('/api/suppliers', methods=['GET', 'POST'])
@login_required
def api_suppliers():
    if request.method == 'GET':
        suppliers = Supplier.query.all()
        return jsonify([{
            'id': supplier.id,
            'name': supplier.name,
            'contact_no': supplier.contact_no,
            'address': supplier.address
        } for supplier in suppliers])
    
    elif request.method == 'POST':
        if not current_user.can_manage_suppliers():
            return jsonify({'error': 'Insufficient permissions'}), 403
        
        data = request.get_json()
        supplier = Supplier(
            name=data['name'],
            contact_no=data.get('contact_no', ''),
            address=data.get('address', '')
        )
        
        db.session.add(supplier)
        db.session.commit()
        
        log_audit('create', 'suppliers', supplier.id, None, data, current_user.id)
        create_notification(current_user.id, 'New Supplier Added', f'Supplier {supplier.name} has been added to the system.', 'success', 'inventory')
        
        return jsonify({
            'success': True,
            'supplier': {
                'id': supplier.id,
                'name': supplier.name,
                'contact_no': supplier.contact_no,
                'address': supplier.address
            }
        })

# Expenses API
@app.route('/api/expenses', methods=['GET', 'POST'])
@login_required
def api_expenses():
    if request.method == 'GET':
        expenses = Expense.query.order_by(Expense.expense_date.desc()).all()
        return jsonify([{
            'id': expense.id,
            'expense_date': expense.expense_date.isoformat(),
            'category': expense.category,
            'description': expense.description,
            'amount': expense.amount,
            'payment_method': expense.payment_method,
            'receipt_number': expense.receipt_number,
            'creator_name': expense.creator.name if expense.creator else 'Unknown'
        } for expense in expenses])
    
    elif request.method == 'POST':
        if not current_user.can_view_reports():
            return jsonify({'error': 'Insufficient permissions'}), 403
        
        data = request.get_json()
        expense = Expense(
            category=data['category'],
            description=data['description'],
            amount=data['amount'],
            payment_method=data['payment_method'],
            receipt_number=data.get('receipt_number', ''),
            created_by=current_user.id
        )
        
        db.session.add(expense)
        db.session.commit()
        
        log_audit('create', 'expenses', expense.id, None, data, current_user.id)
        create_notification(current_user.id, 'New Expense Recorded', f'Expense of ₱{expense.amount:.2f} for {expense.category} has been recorded.', 'info', 'system')
        
        return jsonify({
            'success': True,
            'expense': {
                'id': expense.id,
                'expense_date': expense.expense_date.isoformat(),
                'category': expense.category,
                'description': expense.description,
                'amount': expense.amount,
                'payment_method': expense.payment_method,
                'receipt_number': expense.receipt_number
            }
        })

# Maintenance Logs API
@app.route('/api/maintenance', methods=['GET', 'POST'])
@login_required
def api_maintenance():
    if request.method == 'GET':
        logs = MaintenanceLog.query.order_by(MaintenanceLog.maintenance_date.desc()).all()
        return jsonify([{
            'id': log.id,
            'maintenance_date': log.maintenance_date.isoformat(),
            'maintenance_type': log.maintenance_type,
            'equipment_name': log.equipment_name,
            'description': log.description,
            'cost': log.cost,
            'performed_by': log.performed_by,
            'next_maintenance': log.next_maintenance.isoformat() if log.next_maintenance else None,
            'creator_name': log.creator.name if log.creator else 'Unknown'
        } for log in logs])
    
    elif request.method == 'POST':
        if not current_user.can_manage_inventory():
            return jsonify({'error': 'Insufficient permissions'}), 403
        
        data = request.get_json()
        
        # Parse dates
        maintenance_date = datetime.fromisoformat(data['maintenance_date'].replace('Z', '+00:00'))
        next_maintenance = None
        if data.get('next_maintenance'):
            next_maintenance = datetime.fromisoformat(data['next_maintenance'].replace('Z', '+00:00'))
        
        log = MaintenanceLog(
            maintenance_date=maintenance_date,
            maintenance_type=data['maintenance_type'],
            equipment_name=data['equipment_name'],
            description=data['description'],
            cost=data.get('cost', 0.0),
            performed_by=data.get('performed_by', ''),
            next_maintenance=next_maintenance,
            created_by=current_user.id
        )
        
        db.session.add(log)
        db.session.commit()
        
        log_audit('create', 'maintenance_logs', log.id, None, data, current_user.id)
        create_notification(current_user.id, 'Maintenance Logged', f'Maintenance for {log.equipment_name} has been recorded.', 'info', 'system')
        
        # High cost maintenance notification
        if log.cost > 1000:  # Alert for maintenance over ₱1000
            create_notification_for_role(
                'manager', 
                'High Cost Maintenance', 
                f'Maintenance cost ₱{log.cost:.2f} for {log.equipment_name}', 
                'warning', 
                'maintenance', 
                '/maintenance', 
                'View Maintenance'
            )
        
        return jsonify({
            'success': True,
            'log': {
                'id': log.id,
                'maintenance_date': log.maintenance_date.isoformat(),
                'maintenance_type': log.maintenance_type,
                'equipment_name': log.equipment_name,
                'description': log.description,
                'cost': log.cost,
                'performed_by': log.performed_by,
                'next_maintenance': log.next_maintenance.isoformat() if log.next_maintenance else None
            }
        })

# Maintenance Logs API for parts (inventory integration)
@app.route('/api/maintenance-logs', methods=['GET', 'POST'])
@login_required
def api_maintenance_logs():
    if request.method == 'GET':
        # Filter by part_id if provided
        part_id = request.args.get('part_id')
        if part_id:
            logs = MaintenanceLog.query.filter_by(part_id=part_id).order_by(MaintenanceLog.maintenance_date.desc()).all()
        else:
            logs = MaintenanceLog.query.order_by(MaintenanceLog.maintenance_date.desc()).all()
        
        return jsonify([{
            'id': log.id,
            'part_id': log.part_id,
            'maintenance_date': log.maintenance_date.isoformat(),
            'description': log.description,
            'cost': log.cost,
            'performed_by': log.performed_by,
            'notes': log.notes,
            'creator_name': log.creator.name if log.creator else 'Unknown'
        } for log in logs])
    
    elif request.method == 'POST':
        if not current_user.can_manage_inventory():
            return jsonify({'error': 'Insufficient permissions'}), 403
        
        data = request.get_json()
        
        # Parse date
        maintenance_date = datetime.fromisoformat(data['maintenance_date'].replace('Z', '+00:00'))
        
        log = MaintenanceLog(
            part_id=data.get('part_id'),
            maintenance_date=maintenance_date,
            maintenance_type='inventory',  # Default type for inventory maintenance
            equipment_name=data.get('equipment_name', f'Part ID: {data.get("part_id")}'),
            description=data['description'],
            cost=data.get('cost', 0.0),
            performed_by=data.get('performed_by', current_user.name),
            notes=data.get('notes', ''),
            created_by=current_user.id
        )
        
        db.session.add(log)
        db.session.commit()
        
        log_audit('create', 'maintenance_logs', log.id, None, data, current_user.id)
        create_notification(current_user.id, 'Maintenance Logged', f'Maintenance for part has been recorded.', 'info', 'inventory')
        
        # High cost maintenance notification
        if log.cost > 500:  # Alert for maintenance over ₱500
            create_notification_for_role(
                'manager', 
                'Maintenance Cost Alert', 
                f'Maintenance cost ₱{log.cost:.2f} for inventory item', 
                'warning', 
                'inventory', 
                '/inventory', 
                'View Inventory'
            )
        
        return jsonify({
            'success': True,
            'log': {
                'id': log.id,
                'part_id': log.part_id,
                'maintenance_date': log.maintenance_date.isoformat(),
                'description': log.description,
                'cost': log.cost,
                'performed_by': log.performed_by,
                'notes': log.notes
            }
        })

# Purchase Orders API
@app.route('/api/purchase-orders', methods=['GET', 'POST'])
@login_required
def api_purchase_orders():
    if request.method == 'GET':
        orders = PurchaseOrder.query.order_by(PurchaseOrder.order_date.desc()).all()
        return jsonify([{
            'id': order.id,
            'order_number': order.order_number,
            'supplier_name': order.supplier.name if order.supplier else 'Unknown',
            'order_date': order.order_date.isoformat(),
            'expected_date': order.expected_date.isoformat() if order.expected_date else None,
            'status': order.status,
            'total_amount': order.total_amount,
            'creator_name': order.creator.name if order.creator else 'Unknown'
        } for order in orders])
    
    elif request.method == 'POST':
        if not current_user.can_manage_inventory():
            return jsonify({'error': 'Insufficient permissions'}), 403
        
        data = request.get_json()
        
        # Parse dates
        order_date = datetime.fromisoformat(data['order_date'].replace('Z', '+00:00'))
        expected_date = None
        if data.get('expected_date'):
            expected_date = datetime.fromisoformat(data['expected_date'].replace('Z', '+00:00'))
        
        order = PurchaseOrder(
            order_number=generate_purchase_order_number(),
            supplier_id=data['supplier_id'],
            order_date=order_date,
            expected_date=expected_date,
            status='pending',
            total_amount=0.0,
            created_by=current_user.id
        )
        
        db.session.add(order)
        db.session.flush()  # Get the ID
        
        # Add items
        total_amount = 0.0
        for item_data in data['items']:
            item = PurchaseOrderItem(
                purchase_order_id=order.id,
                part_id=item_data['part_id'],
                quantity=item_data['quantity'],
                unit_price=item_data['unit_price'],
                total_price=item_data['quantity'] * item_data['unit_price']
            )
            db.session.add(item)
            total_amount += item.total_price
        
        order.total_amount = total_amount
        db.session.commit()
        
        log_audit('create', 'purchase_orders', order.id, None, data, current_user.id)
        create_notification(current_user.id, 'Purchase Order Created', f'Purchase order {order.order_number} for ₱{total_amount:.2f} has been created.', 'success', 'inventory')
        
        return jsonify({
            'success': True,
            'order': {
                'id': order.id,
                'order_number': order.order_number,
                'supplier_id': order.supplier_id,
                'order_date': order.order_date.isoformat(),
                'expected_date': order.expected_date.isoformat() if order.expected_date else None,
                'status': order.status,
                'total_amount': order.total_amount
            }
        })

# System Logs API (Admin only)
@app.route('/api/system-logs', methods=['GET'])
@login_required
def api_system_logs():
    if not current_user.is_admin():
        return jsonify({'error': 'Admin access required'}), 403
    
    logs = SystemLog.query.order_by(SystemLog.log_date.desc()).limit(100).all()
    return jsonify([{
        'id': log.id,
        'log_date': log.log_date.isoformat(),
        'log_level': log.log_level,
        'category': log.category,
        'message': log.message,
        'details': log.details,
        'source': log.source
    } for log in logs])

# Audit Logs API (Admin/Manager only)
@app.route('/api/audit-logs', methods=['GET'])
@login_required
def api_audit_logs():
    if not (current_user.is_admin() or current_user.is_manager()):
        return jsonify({'error': 'Manager access required'}), 403
    
    logs = AuditLog.query.order_by(AuditLog.action_date.desc()).limit(100).all()
    return jsonify([{
        'id': log.id,
        'action_date': log.action_date.isoformat(),
        'user_name': log.user.name if log.user else 'System',
        'action_type': log.action_type,
        'table_name': log.table_name,
        'record_id': log.record_id,
        'ip_address': log.ip_address,
        'user_agent': log.user_agent
    } for log in logs])

# Backup API (Admin only)
@app.route('/api/backup', methods=['POST'])
@login_required
def api_backup():
    if not current_user.is_admin():
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        # Create backup log entry
        backup = BackupLog(
            backup_type='manual',
            status='in_progress',
            created_by=current_user.id
        )
        db.session.add(backup)
        db.session.flush()
        
        # Simulate backup process (in real implementation, this would create actual backup)
        import time
        time.sleep(2)  # Simulate backup time
        
        backup.status = 'success'
        backup.backup_location = f'/backups/jrf_system_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.sql'
        backup.file_size = 1024 * 1024  # 1MB sample size
        
        db.session.commit()
        
        log_audit('create', 'backup_logs', backup.id, None, {'backup_type': 'manual'}, current_user.id)
        create_notification(current_user.id, 'Backup Completed', f'System backup has been completed successfully.', 'success', 'backup')
        
        return jsonify({
            'success': True,
            'backup': {
                'id': backup.id,
                'backup_date': backup.backup_date.isoformat(),
                'backup_type': backup.backup_type,
                'status': backup.status,
                'backup_location': backup.backup_location,
                'file_size': backup.file_size
            }
        })
        
    except Exception as e:
        db.session.rollback()
        log_system('error', f'Backup failed: {str(e)}', 'backup')
        return jsonify({'error': 'Backup failed'}), 500

# API Routes
@app.route('/api/parts', methods=['GET', 'POST'])
@login_required
def handle_parts():
    # GET: All users can view parts
    # POST: Only admin/manager can add parts
    if request.method == 'GET':
        parts = Part.query.all()
        return jsonify([{
            'part_id': part.id,
            'id': part.id,
            'name': part.name,
            'part_type': part.part_type,
            'brand': part.brand,
            'price': part.price,
            'stock_quantity': part.stock_quantity,
            'description': part.description,
            'suppliers': [{
                'id': supplier.id,
                'name': supplier.name
            } for supplier in part.suppliers]
        } for part in parts])
    
    # POST - Add new part (admin/manager only)
    if not current_user.can_manage_inventory():
        return jsonify({'success': False, 'message': 'Permission denied. Admin or Manager access required.'}), 403
    
    data = request.get_json()
    new_part = Part(
        name=data['name'],
        part_type=data.get('part_type'),
        brand=data.get('brand'),
        price=float(data['price']),
        stock_quantity=int(data.get('stock_quantity', 0)),
        description=data.get('description')
    )
    db.session.add(new_part)
    db.session.flush()  # Get the part ID
    
    # Add suppliers if provided
    if data.get('supplier_ids'):
        for supplier_id in data['supplier_ids']:
            supplier = Supplier.query.get(supplier_id)
            if supplier:
                new_part.suppliers.append(supplier)
    
    db.session.commit()
    return jsonify({'success': True, 'message': 'Part added successfully'}), 201

@app.route('/api/sales', methods=['POST'])
@login_required
def process_sale():
    """Process a new sale and save to database"""
    try:
        data = request.get_json()
        
        # Extract total amount and payment method
        total_amount = float(data['total'])
        payment_method = data['paymentMethod']
        
        # Create sale record
        new_sale = Sale(
            total_amount=total_amount,
            payment_method=payment_method,
            staff_id=current_user.id,
            customer_id=data.get('customer_id'),  # Add customer support
            receipt_number=generate_receipt_number(),  # Add receipt number
            notes=data.get('notes', '')  # Add notes field
        )
        
        db.session.add(new_sale)
        db.session.flush()  # Get the sale ID
        
        # Extract items from data
        items = data['items']
        
        # Create sale details and update stock
        low_stock_items = []
        # Get low stock threshold from settings
        threshold_setting = Settings.query.filter_by(category='inventory', setting_key='low_stock_threshold').first()
        low_stock_threshold = int(threshold_setting.setting_value) if threshold_setting else 5
        
        for item in items:
            sale_detail = SaleDetail(
                sale_id=new_sale.id,
                part_id=item['id'],
                quantity=item['quantity'],
                price_at_sale=float(item['price'])
            )
            db.session.add(sale_detail)
            
            # Update part stock
            part = Part.query.get(item['id'])
            if part:
                old_stock = part.stock_quantity
                part.stock_quantity -= item['quantity']
                if part.stock_quantity < 0:
                    part.stock_quantity = 0
                
                # Check for low stock and collect parts that dropped below threshold
                if part.stock_quantity < low_stock_threshold and part.stock_quantity >= 0:
                    low_stock_items.append(part)
        
        db.session.commit()
        
        # Create notifications after commit
        # 1) Critical low stock notifications for managers (only very low stock)
        for part in low_stock_items:
            if part.stock_quantity <= 2:  # Only notify for very low stock
                create_notification_for_role(
                    'manager', 
                    'Critical Stock Alert', 
                    f'{part.name} is critically low on stock ({part.stock_quantity} remaining)', 
                    'warning', 
                    'inventory', 
                    '/inventory', 
                    'View Inventory'
                )
        
        # 2) Sale completion notification for the staff who processed the sale
        sale_identifier = new_sale.receipt_number or f'Sale #{new_sale.id}'
        create_notification(
            current_user.id,
            'Sale Completed',
            f'{sale_identifier} completed for ₱{total_amount:.2f}.',
            'success',
            'sales',
            '/sales',
            'View Sale'
        )

        # 3) High value sale alerts for managers and admins
        try:
            high_value_threshold_setting = Settings.query.filter_by(
                category='sales', setting_key='high_value_sale_threshold'
            ).first()
            high_value_threshold = float(high_value_threshold_setting.setting_value) if high_value_threshold_setting else 5000.0
        except Exception:
            high_value_threshold = 5000.0

        if total_amount >= high_value_threshold:
            message = f'High value sale of ₱{total_amount:.2f} processed by {current_user.name}.'
            create_notification_for_role(
                'manager',
                'High Value Sale',
                message,
                'warning',
                'sales',
                '/reports',
                'View Reports'
            )
            create_notification_for_role(
                'admin',
                'High Value Sale',
                message,
                'warning',
                'sales',
                '/reports',
                'View Reports'
            )

        # 4) Sales milestone notifications every 10 sales
        try:
            total_sales_count = Sale.query.count()
            if total_sales_count > 0 and total_sales_count % 10 == 0:
                milestone_message = f'{total_sales_count} total sales have been completed.'
                create_notification_for_role(
                    'manager',
                    'Sales Milestone Reached',
                    milestone_message,
                    'info',
                    'sales',
                    '/reports',
                    'View Reports'
                )
                create_notification_for_role(
                    'admin',
                    'Sales Milestone Reached',
                    milestone_message,
                    'info',
                    'sales',
                    '/reports',
                    'View Reports'
                )
        except Exception:
            # If counting sales fails for any reason, do not block the main sale flow
            pass

        # Log the sale
        log_audit('create', 'sales', new_sale.id, None, {
            'total_amount': total_amount,
            'payment_method': payment_method,
            'customer_id': data.get('customer_id'),
            'items': items
        }, current_user.id)
        
        return jsonify({
            'success': True, 
            'message': 'Sale processed successfully',
            'sale_id': new_sale.id,
            'receipt_number': new_sale.receipt_number
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False, 
            'message': f'Error processing sale: {str(e)}'
        }), 500

@app.route('/api/recent-activities')
@login_required
def get_recent_activities():
    """Get recent activities including sales"""
    activities = []
    
    # Add recent sales
    recent_sales = Sale.query.order_by(Sale.sale_date.desc()).limit(5).all()
    for sale in recent_sales:
        activities.append({
            'message': f"New sale completed - ₱{sale.total_amount:.2f}",
            'timestamp': sale.sale_date,
            'icon': 'fas fa-shopping-cart',
            'icon_bg': 'bg-green-500'
        })
    
    # Add low stock alerts
    low_stock_parts = Part.query.filter(Part.stock_quantity < 5).limit(3).all()
    for part in low_stock_parts:
        activities.append({
            'message': f"Low stock alert: {part.name} ({part.stock_quantity} left)",
            'timestamp': datetime.utcnow(),
            'icon': 'fas fa-exclamation-triangle',
            'icon_bg': 'bg-yellow-500'
        })
    
    # Sort by timestamp
    activities.sort(key=lambda x: x['timestamp'], reverse=True)
    
    return jsonify(activities[:10])  # Return top 10 activities

@app.route('/api/todays-sales')
@login_required
def get_todays_sales():
    """Get today's sales data for reports"""
    from datetime import datetime
    
    # Get today's date (start and end)
    today = datetime.utcnow().date()
    start_of_day = datetime.combine(today, datetime.min.time())
    end_of_day = datetime.combine(today, datetime.max.time())
    
    # Today's sales with details
    todays_sales = db.session.query(
        Sale.id,
        Sale.sale_date,
        Sale.total_amount,
        Sale.payment_method,
        User.name.label('staff_name'),
        Customer.name.label('customer_name'),
        Customer.email.label('customer_email'),
        db.func.count(SaleDetail.part_id).label('items_count')
    ).join(User).join(SaleDetail).join(Customer, Sale.customer_id == Customer.id, isouter=True).filter(
        Sale.sale_date >= start_of_day,
        Sale.sale_date <= end_of_day
    ).group_by(Sale.id, User.name, Customer.name, Customer.email).order_by(Sale.sale_date.desc()).all()
    
    # Today's summary
    todays_summary = db.session.query(
        db.func.count(Sale.id).label('total_sales'),
        db.func.sum(Sale.total_amount).label('total_revenue'),
        db.func.avg(Sale.total_amount).label('avg_sale_value')
    ).filter(
        Sale.sale_date >= start_of_day,
        Sale.sale_date <= end_of_day
    ).first()
    
    return jsonify({
        'sales': [
            {
                'id': sale.id,
                'sale_date': sale.sale_date.isoformat(),
                'total_amount': float(sale.total_amount),
                'payment_method': sale.payment_method,
                'staff_name': sale.staff_name,
                'customer_name': sale.customer_name or 'Walk-in Customer',
                'customer_email': sale.customer_email,
                'items_count': sale.items_count
            } for sale in todays_sales
        ],
        'summary': {
            'total_sales': todays_summary.total_sales or 0,
            'total_revenue': float(todays_summary.total_revenue or 0),
            'avg_sale_value': float(todays_summary.avg_sale_value or 0)
        }
    })

@app.route('/api/sales-data')
@manager_required
def get_sales_data():
    """Get comprehensive sales data for reports"""
    from datetime import datetime, timedelta
    
    # Sales by day for last 30 days
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    
    sales_by_day = db.session.query(
        db.func.date(Sale.sale_date).label('date'),
        db.func.count(Sale.id).label('count'),
        db.func.sum(Sale.total_amount).label('total')
    ).filter(Sale.sale_date >= thirty_days_ago
    ).group_by(db.func.date(Sale.sale_date)
    ).order_by(db.func.date(Sale.sale_date)).all()
    
    # Sales by staff (all-time performance)
    sales_by_staff = db.session.query(
        User.name,
        db.func.count(Sale.id).label('count'),
        db.func.sum(Sale.total_amount).label('total'),
        db.func.avg(Sale.total_amount).label('avg_sale')
    ).join(Sale).group_by(User.id, User.name
    ).order_by(db.func.count(Sale.id).desc()).all()
    
    # Overall statistics (matching dashboard)
    total_parts = Part.query.count()
    low_stock_parts = Part.query.filter(Part.stock_quantity < 5).count()
    total_sales = Sale.query.count()
    total_suppliers = Supplier.query.count()
    
    # Total revenue (all time)
    total_revenue = db.session.query(db.func.sum(Sale.total_amount)).scalar() or 0
    
    # Recent sales (last 7 days)
    week_ago = datetime.utcnow() - timedelta(days=7)
    recent_sales_count = Sale.query.filter(Sale.sale_date >= week_ago).count()
    
    # ALL top selling parts (not just top 5)
    top_parts = db.session.query(
        Part.name,
        Part.brand,
        Part.part_type,
        db.func.sum(SaleDetail.quantity).label('total_sold'),
        db.func.sum(SaleDetail.quantity * SaleDetail.price_at_sale).label('revenue'),
        Part.stock_quantity
    ).join(SaleDetail).group_by(Part.id, Part.name, Part.brand, Part.part_type, Part.stock_quantity
    ).order_by(db.func.sum(SaleDetail.quantity).desc()
    ).all()
    
    # ALL low stock items with details
    low_stock_items = db.session.query(
        Part.id,
        Part.name,
        Part.brand,
        Part.part_type,
        Part.stock_quantity,
        Part.price,
        db.func.sum(SaleDetail.quantity).label('total_sold')
    ).outerjoin(SaleDetail).group_by(Part.id, Part.name, Part.brand, Part.part_type, Part.stock_quantity, Part.price
    ).filter(Part.stock_quantity < 5
    ).order_by(Part.stock_quantity.asc()).all()
    
    # Revenue by category
    revenue_by_category = db.session.query(
        Part.part_type,
        db.func.sum(SaleDetail.quantity * SaleDetail.price_at_sale).label('revenue')
    ).join(SaleDetail).group_by(Part.part_type
    ).filter(Part.part_type.isnot(None)
    ).order_by(db.func.sum(SaleDetail.quantity * SaleDetail.price_at_sale).desc()
    ).all()
    
    return jsonify({
        'sales_by_day': [
            {
                'date': str(sale.date),
                'count': sale.count,
                'total': float(sale.total or 0)
            } for sale in sales_by_day
        ],
        'sales_by_staff': [
            {
                'name': staff.name,
                'count': staff.count,
                'total': float(staff.total or 0),
                'avg_sale': float(staff.avg_sale or 0)
            } for staff in sales_by_staff
        ],
        'statistics': {
            'total_parts': total_parts,
            'low_stock_parts': low_stock_parts,
            'total_sales': total_sales,
            'total_suppliers': total_suppliers,
            'total_revenue': float(total_revenue),
            'recent_sales': recent_sales_count
        },
        'top_parts': [
            {
                'name': part.name,
                'brand': part.brand,
                'category': part.part_type,
                'units_sold': int(part.total_sold or 0),
                'revenue': float(part.revenue or 0),
                'stock_quantity': part.stock_quantity
            } for part in top_parts
        ],
        'low_stock_items': [
            {
                'id': item.id,
                'name': item.name,
                'brand': item.brand,
                'category': item.part_type,
                'stock_quantity': item.stock_quantity,
                'price': float(item.price),
                'total_sold': int(item.total_sold or 0)
            } for item in low_stock_items
        ],
        'revenue_by_category': [
            {
                'category': category.part_type or 'Other',
                'revenue': float(category.revenue or 0)
            } for category in revenue_by_category
        ]
    })

@app.route('/api/suppliers', methods=['GET', 'POST'])
@login_required
def manage_suppliers():
    """Get all suppliers or create new supplier"""
    if not current_user.can_manage_suppliers():
        return jsonify({'success': False, 'message': 'Permission denied. Admin or Manager access required.'}), 403
    
    if request.method == 'GET':
        suppliers = Supplier.query.all()
        return jsonify([{
            'id': supplier.id,
            'name': supplier.name,
            'contact_no': supplier.contact_no,
            'address': supplier.address
        } for supplier in suppliers])
    
    elif request.method == 'POST':
        data = request.get_json()
        
        # Validate required fields
        if not data.get('name'):
            return jsonify({'success': False, 'message': 'Supplier name is required'}), 400
        
        # Check if supplier already exists
        existing = Supplier.query.filter_by(name=data['name']).first()
        if existing:
            return jsonify({'success': False, 'message': 'Supplier with this name already exists'}), 400
        
        # Create new supplier
        supplier = Supplier(
            name=data['name'],
            contact_no=data.get('contact_no', ''),
            address=data.get('address', '')
        )
        
        db.session.add(supplier)
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': 'Supplier added successfully',
            'supplier': {
                'id': supplier.id,
                'name': supplier.name,
                'contact_no': supplier.contact_no,
                'address': supplier.address
            }
        })

@app.route('/api/suppliers/<int:supplier_id>', methods=['PUT', 'DELETE'])
@login_required
def handle_supplier(supplier_id):
    """Update or delete supplier"""
    if not current_user.can_manage_suppliers():
        return jsonify({'success': False, 'message': 'Permission denied. Admin or Manager access required.'}), 403
    
    supplier = Supplier.query.get_or_404(supplier_id)
    
    if request.method == 'DELETE':
        # Check if supplier has parts
        if supplier.parts:
            return jsonify({'success': False, 'message': 'Cannot delete supplier with associated parts'}), 400
        
        db.session.delete(supplier)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Supplier deleted successfully'})
    
    elif request.method == 'PUT':
        data = request.get_json()
        
        # Validate required fields
        if not data.get('name'):
            return jsonify({'success': False, 'message': 'Supplier name is required'}), 400
        
        # Check if name conflicts with another supplier
        existing = Supplier.query.filter(Supplier.name == data['name'], Supplier.id != supplier_id).first()
        if existing:
            return jsonify({'success': False, 'message': 'Supplier with this name already exists'}), 400
        
        # Update supplier
        supplier.name = data['name']
        supplier.contact_no = data.get('contact_no', '')
        supplier.address = data.get('address', '')
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': 'Supplier updated successfully',
            'supplier': {
                'id': supplier.id,
                'name': supplier.name,
                'contact_no': supplier.contact_no,
                'address': supplier.address
            }
        })
    
    elif request.method == 'PUT':
        data = request.get_json()
        
        # Validate required fields
        if not data.get('name'):
            return jsonify({'success': False, 'message': 'Supplier name is required'}), 400
        
        # Check if name conflicts with another supplier
        existing = Supplier.query.filter(Supplier.name == data['name'], Supplier.id != supplier_id).first()
        if existing:
            return jsonify({'success': False, 'message': 'Supplier with this name already exists'}), 400
        
        # Update supplier
        supplier.name = data['name']
        supplier.contact_no = data.get('contact_no', '')
        supplier.address = data.get('address', '')
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': 'Supplier updated successfully',
            'supplier': {
                'id': supplier.id,
                'name': supplier.name,
                'contact_no': supplier.contact_no,
                'address': supplier.address
            }
        })

@app.route('/api/parts/<int:part_id>/suppliers', methods=['GET', 'POST', 'DELETE'])
@login_required
def manage_part_suppliers(part_id):
    """Manage suppliers for a specific part"""
    if not current_user.can_manage_inventory():
        return jsonify({'success': False, 'message': 'Permission denied. Admin or Manager access required.'}), 403
    
    part = Part.query.get_or_404(part_id)
    
    if request.method == 'GET':
        # Get all suppliers for this part
        suppliers = part.suppliers
        return jsonify([{
            'id': supplier.id,
            'name': supplier.name,
            'contact_no': supplier.contact_no,
            'address': supplier.address
        } for supplier in suppliers])
    
    elif request.method == 'POST':
        # Add supplier to part
        data = request.get_json()
        supplier_id = data.get('supplier_id')
        
        if not supplier_id:
            return jsonify({'success': False, 'message': 'Supplier ID is required'}), 400
        
        supplier = Supplier.query.get_or_404(supplier_id)
        
        # Check if already associated
        if supplier in part.suppliers:
            return jsonify({'success': False, 'message': 'Supplier already associated with this part'}), 400
        
        # Add association
        part.suppliers.append(supplier)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Supplier added to part successfully'})
    
    elif request.method == 'DELETE':
        # Remove supplier from part
        data = request.get_json()
        supplier_id = data.get('supplier_id')
        
        if not supplier_id:
            return jsonify({'success': False, 'message': 'Supplier ID is required'}), 400
        
        supplier = Supplier.query.get_or_404(supplier_id)
        
        # Remove association
        if supplier in part.suppliers:
            part.suppliers.remove(supplier)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Supplier removed from part successfully'})
        else:
            return jsonify({'success': False, 'message': 'Supplier not associated with this part'}), 404

@app.route('/api/parts/<int:part_id>', methods=['PUT', 'DELETE'])
@login_required
def handle_part(part_id):
    # Only admin/manager can edit/delete parts
    if not current_user.can_manage_inventory():
        return jsonify({'success': False, 'message': 'Permission denied. Admin or Manager access required.'}), 403
    
    part = Part.query.get_or_404(part_id)
    
    if request.method == 'PUT':
        data = request.get_json()
        part.name = data.get('name', part.name)
        part.part_type = data.get('part_type', part.part_type)
        part.brand = data.get('brand', part.brand)
        part.price = float(data.get('price', part.price))
        part.stock_quantity = int(data.get('stock_quantity', part.stock_quantity))
        part.description = data.get('description', part.description)
        
        # Update supplier relationships
        if 'supplier_ids' in data:
            # Clear existing suppliers
            part.suppliers.clear()
            
            # Add new suppliers
            if data['supplier_ids']:
                for supplier_id in data['supplier_ids']:
                    supplier = Supplier.query.get(supplier_id)
                    if supplier:
                        part.suppliers.append(supplier)
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'Part updated successfully'})
    
    elif request.method == 'DELETE':
        db.session.delete(part)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Part deleted successfully'})

@app.route('/api/parts/<int:part_id>/sales-metrics', methods=['GET'])
@login_required
def get_part_sales_metrics(part_id):
    """Get aggregated sales metrics for a part"""
    metrics = db.session.query(
        db.func.coalesce(db.func.sum(SaleDetail.quantity), 0).label('total_sold'),
        db.func.coalesce(db.func.sum(SaleDetail.quantity * SaleDetail.price_at_sale), 0.0).label('total_revenue')
    ).filter(SaleDetail.part_id == part_id).first()

    total_sold = int(metrics.total_sold or 0)
    total_revenue = float(metrics.total_revenue or 0.0)
    avg_price = float(total_revenue / total_sold) if total_sold > 0 else 0.0

    return jsonify({
        'total_sold': total_sold,
        'total_revenue': total_revenue,
        'avg_price': avg_price
    })
@manager_required
def handle_suppliers():
    if request.method == 'GET':
        suppliers = Supplier.query.all()
        return jsonify([{
            'id': supplier.id,
            'name': supplier.name,
            'contact_no': supplier.contact_no,
            'address': supplier.address,
            'parts_count': len(supplier.parts)
        } for supplier in suppliers])
    
    # POST - Add new supplier
    data = request.get_json()
    new_supplier = Supplier(
        name=data['name'],
        contact_no=data.get('contact_no'),
        address=data.get('address')
    )
    db.session.add(new_supplier)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Supplier added successfully'}), 201

@app.route('/api/staff', methods=['GET', 'POST'])
@admin_required
def handle_staff():
    if request.method == 'GET':
        staff = User.query.all()
        return jsonify([{
            'id': user.id,
            'name': user.name,
            'email': user.email,
            'username': user.username,
            'role': user.role,
            'contact_no': user.contact_no,
            'sales_count': len(user.sales)
        } for user in staff])
    
    # POST - Add new staff member
    data = request.get_json()
    new_user = User(
        name=data['name'],
        email=data['email'],
        username=data['username'],
        role=data.get('role', 'staff'),
        contact_no=data.get('contact_no')
    )
    new_user.set_password(data['password'])
    db.session.add(new_user)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Staff member added successfully'}), 201

@app.route('/api/staff/<int:staff_id>', methods=['PUT', 'DELETE'])
@admin_required
def handle_staff_member(staff_id):
    user = User.query.get_or_404(staff_id)
    
    if request.method == 'PUT':
        data = request.get_json()
        user.name = data.get('name', user.name)
        user.email = data.get('email', user.email)
        user.username = data.get('username', user.username)
        user.role = data.get('role', user.role)
        user.contact_no = data.get('contact_no', user.contact_no)
        
        if data.get('password'):
            user.set_password(data['password'])
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'Staff member updated successfully'})
    
    elif request.method == 'DELETE':
        if user.id == current_user.id:
            return jsonify({'success': False, 'message': 'Cannot delete your own account'}), 400
        
        db.session.delete(user)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Staff member deleted successfully'})

@app.route('/api/dashboard/stats', methods=['GET'])
@login_required
def get_dashboard_stats():
    # Get low stock threshold from settings
    threshold_setting = Settings.query.filter_by(category='inventory', setting_key='low_stock_threshold').first()
    low_stock_threshold = int(threshold_setting.setting_value) if threshold_setting else 5
    
    total_parts = Part.query.count()
    low_stock_parts = Part.query.filter(Part.stock_quantity < low_stock_threshold).count()
    total_sales = Sale.query.count()
    total_suppliers = Supplier.query.count()
    total_staff = User.query.count()
    
    # Recent sales (last 7 days)
    from datetime import datetime, timedelta
    week_ago = datetime.utcnow() - timedelta(days=7)
    recent_sales = Sale.query.filter(Sale.sale_date >= week_ago).count()
    
    return jsonify({
        'total_parts': total_parts,
        'low_stock_parts': low_stock_parts,
        'total_sales': total_sales,
        'total_suppliers': total_suppliers,
        'total_staff': total_staff,
        'recent_sales': recent_sales
    })

# API Routes using Stored Procedures and Functions
@app.route('/api/low-stock-parts', methods=['GET'])
@login_required
def get_low_stock_parts():
    """Get low stock parts using stored procedure"""
    try:
        threshold = int(request.args.get('threshold', 5))
        
        # Use stored procedure: GetLowStockParts
        result = db.session.execute(
            text('CALL GetLowStockParts(:threshold)'),
            {'threshold': threshold}
        )
        
        parts = []
        for row in result:
            parts.append({
                'id': row[0],
                'name': row[1],
                'part_type': row[2],
                'brand': row[3],
                'price': float(row[4]),
                'stock_quantity': row[5],
                'description': row[6],
                'stock_status': db.session.execute(
                    text('SELECT GetStockStatus(:qty)'),
                    {'qty': row[5]}
                ).scalar()
            })
        
        return jsonify(parts)
    except Exception as e:
        # Fallback to regular query if stored procedure doesn't exist
        threshold = int(request.args.get('threshold', 5))
        parts = Part.query.filter(Part.stock_quantity < threshold).all()
        return jsonify([{
            'id': part.id,
            'name': part.name,
            'part_type': part.part_type,
            'brand': part.brand,
            'price': part.price,
            'stock_quantity': part.stock_quantity,
            'description': part.description
        } for part in parts])

@app.route('/api/monthly-sales', methods=['GET'])
@manager_required
def get_monthly_sales():
    """Calculate monthly sales using stored procedure"""
    try:
        year = int(request.args.get('year', datetime.utcnow().year))
        month = int(request.args.get('month', datetime.utcnow().month))
        
        # Use stored procedure: CalculateMonthlySales
        result = db.session.execute(
            text('CALL CalculateMonthlySales(:year, :month, @total_sales, @total_count)'),
            {'year': year, 'month': month}
        )
        
        # Get output parameters
        result = db.session.execute(text('SELECT @total_sales, @total_count'))
        row = result.fetchone()
        
        total_sales = float(row[0]) if row[0] else 0.0
        total_count = int(row[1]) if row[1] else 0
        
        return jsonify({
            'year': year,
            'month': month,
            'total_sales': total_sales,
            'total_count': total_count,
            'formatted_total': db.session.execute(
                text('SELECT FormatCurrency(:amount)'),
                {'amount': total_sales}
            ).scalar()
        })
    except Exception as e:
        # Fallback to regular query
        from datetime import datetime
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1)
        else:
            end_date = datetime(year, month + 1, 1)
        
        sales = Sale.query.filter(
            Sale.sale_date >= start_date,
            Sale.sale_date < end_date
        ).all()
        
        total_sales = sum(sale.total_amount for sale in sales)
        
        return jsonify({
            'year': year,
            'month': month,
            'total_sales': total_sales,
            'total_count': len(sales)
        })

@app.route('/api/sales-report-by-staff', methods=['GET'])
@manager_required
def get_sales_report_by_staff():
    """Get sales report by staff using stored procedure"""
    try:
        start_date = request.args.get('start_date', (datetime.utcnow() - timedelta(days=30)).strftime('%Y-%m-%d'))
        end_date = request.args.get('end_date', datetime.utcnow().strftime('%Y-%m-%d'))
        
        # Use stored procedure: GetSalesReportByStaff
        result = db.session.execute(
            text('CALL GetSalesReportByStaff(:start_date, :end_date)'),
            {'start_date': start_date, 'end_date': end_date}
        )
        
        report = []
        for row in result:
            report.append({
                'staff_id': row[0],
                'staff_name': row[1],
                'role': row[2],
                'total_sales_count': row[3],
                'total_sales_amount': float(row[4]),
                'average_sale_amount': float(row[5]),
                'formatted_total': db.session.execute(
                    text('SELECT FormatCurrency(:amount)'),
                    {'amount': row[4]}
                ).scalar()
            })
        
        return jsonify(report)
    except Exception as e:
        # Fallback to regular query
        from datetime import datetime
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        
        sales_by_staff = db.session.query(
            User.name,
            db.func.count(Sale.id).label('count'),
            db.func.sum(Sale.total_amount).label('total')
        ).join(Sale).filter(
            Sale.sale_date >= start,
            Sale.sale_date <= end
        ).group_by(User.id, User.name).all()
        
        return jsonify([{
            'staff_name': staff.name,
            'total_sales_count': staff.count,
            'total_sales_amount': float(staff.total or 0)
        } for staff in sales_by_staff])

@app.route('/api/calculate-discount', methods=['POST'])
@login_required
def calculate_discount():
    """Calculate discount using function"""
    try:
        data = request.get_json()
        price = float(data.get('price', 0))
        discount_percent = float(data.get('discount_percent', 0))
        
        # Use function: CalculateDiscount
        result = db.session.execute(
            text('SELECT CalculateDiscount(:price, :discount)'),
            {'price': price, 'discount': discount_percent}
        )
        discount_amount = float(result.scalar())
        
        final_price = price - discount_amount
        
        return jsonify({
            'original_price': price,
            'discount_percent': discount_percent,
            'discount_amount': discount_amount,
            'final_price': final_price,
            'formatted_original': db.session.execute(
                text('SELECT FormatCurrency(:amount)'),
                {'amount': price}
            ).scalar(),
            'formatted_discount': db.session.execute(
                text('SELECT FormatCurrency(:amount)'),
                {'amount': discount_amount}
            ).scalar(),
            'formatted_final': db.session.execute(
                text('SELECT FormatCurrency(:amount)'),
                {'amount': final_price}
            ).scalar()
        })
    except Exception as e:
        # Fallback calculation
        discount_amount = price * (discount_percent / 100)
        return jsonify({
            'original_price': price,
            'discount_percent': discount_percent,
            'discount_amount': discount_amount,
            'final_price': price - discount_amount
        })

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
