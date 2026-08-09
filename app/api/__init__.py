"""
API package - exports all blueprints
"""

from app.api.auth import auth_bp
from app.api.customers import customers_bp
from app.api.dashboard import dashboard_bp
from app.api.notifications import notifications_bp
from app.api.parts import parts_bp
from app.api.realtime import realtime_bp
from app.api.reports import reports_bp
from app.api.sales import sales_bp
from app.api.settings import settings_bp
from app.api.staff import staff_bp
from app.api.suppliers import suppliers_bp
from app.api.system import system_bp

__all__ = [
    "auth_bp",
    "customers_bp",
    "dashboard_bp",
    "notifications_bp",
    "parts_bp",
    "realtime_bp",
    "reports_bp",
    "sales_bp",
    "settings_bp",
    "staff_bp",
    "suppliers_bp",
    "system_bp",
]
