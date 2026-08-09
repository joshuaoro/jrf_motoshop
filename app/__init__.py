"""
JRF Motorcycle Parts Management System

The application is built with the factory pattern - import ``create_app`` and
call it to build an instance. Note that no app is created at import time on
purpose: importing a model or service must never spin up a Flask app, bind a
database engine, or read the environment as a side effect.

    from app import create_app
    app = create_app('production')
"""

from app.core.config import Config, get_config, config
from app.core.factory import create_app
from app.core.extensions import db, login_manager, migrate, csrf
from app.models import (
    User,
    Part,
    Supplier,
    StockEntry,
    supplier_part,
    Customer,
    Sale,
    SaleDetail,
    Payment,
    PurchaseOrder,
    PurchaseOrderItem,
    Expense,
    MaintenanceLog,
    Settings,
    Notification,
    AuditLog,
    SystemLog,
    BackupLog,
)

__version__ = "2.0.3"

__all__ = [
    "__version__",
    "Config",
    "get_config",
    "config",
    "create_app",
    "db",
    "login_manager",
    "migrate",
    "csrf",
    "User",
    "Part",
    "Supplier",
    "StockEntry",
    "supplier_part",
    "Customer",
    "Sale",
    "SaleDetail",
    "Payment",
    "PurchaseOrder",
    "PurchaseOrderItem",
    "Expense",
    "MaintenanceLog",
    "Settings",
    "Notification",
    "AuditLog",
    "SystemLog",
    "BackupLog",
]
