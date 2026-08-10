"""
JRF Motorcycle Parts Management System

The application is built with the factory pattern - import ``create_app`` and
call it to build an instance. Note that no app is created at import time on
purpose: importing a model or service must never spin up a Flask app, bind a
database engine, or read the environment as a side effect.

    from app import create_app
    app = create_app('production')
"""

from app.core.config import Config, config, get_config
from app.core.extensions import csrf, db, login_manager, migrate
from app.core.factory import create_app
from app.models import (
    AuditLog,
    BackupLog,
    Customer,
    Expense,
    MaintenanceLog,
    Notification,
    Part,
    Payment,
    PurchaseOrder,
    PurchaseOrderItem,
    Sale,
    SaleDetail,
    Settings,
    StockEntry,
    Supplier,
    SystemLog,
    User,
    supplier_part,
)

__version__ = "2.0.3"

__all__ = [
    "AuditLog",
    "BackupLog",
    "Config",
    "Customer",
    "Expense",
    "MaintenanceLog",
    "Notification",
    "Part",
    "Payment",
    "PurchaseOrder",
    "PurchaseOrderItem",
    "Sale",
    "SaleDetail",
    "Settings",
    "StockEntry",
    "Supplier",
    "SystemLog",
    "User",
    "__version__",
    "config",
    "create_app",
    "csrf",
    "db",
    "get_config",
    "login_manager",
    "migrate",
    "supplier_part",
]
