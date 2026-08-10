"""
Database models - Purchase Orders, Expenses, Maintenance
"""

from app.core.extensions import db
from app.core.time_utils import now_utc
import uuid


class PurchaseOrder(db.Model):
    """Purchase orders to suppliers"""

    __tablename__ = "purchase_orders"

    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    supplier_id = db.Column(
        db.Integer,
        db.ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    order_date = db.Column(db.DateTime, default=now_utc, nullable=False, index=True)
    expected_date = db.Column(db.DateTime, index=True)
    received_date = db.Column(db.DateTime)
    status = db.Column(
        db.String(20), default="pending", nullable=False, index=True
    )  # pending, ordered, partial, received, cancelled
    subtotal = db.Column(db.Numeric(10, 2), default=0)
    tax_amount = db.Column(db.Numeric(10, 2), default=0)
    shipping_cost = db.Column(db.Numeric(10, 2), default=0)
    total_amount = db.Column(db.Numeric(10, 2), default=0)
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey("staff.id"))
    created_at = db.Column(db.DateTime, default=now_utc, nullable=False)
    updated_at = db.Column(db.DateTime, default=now_utc, onupdate=now_utc)

    # Relationships
    items = db.relationship(
        # selectin, not dynamic: an order's lines are a small bounded set that
        # every caller wants in full, and a dynamic relationship cannot be
        # eager-loaded ("does not support object population").
        "PurchaseOrderItem",
        backref="purchase_order",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    @staticmethod
    def generate_order_number() -> str:
        return f"PO-{now_utc().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

    def to_dict(self, include_items: bool = False) -> dict:
        data = {
            "id": self.id,
            "order_number": self.order_number,
            "supplier_id": self.supplier_id,
            "supplier_name": self.supplier.name if self.supplier else None,
            "order_date": self.order_date.isoformat() if self.order_date else None,
            "expected_date": self.expected_date.isoformat() if self.expected_date else None,
            "received_date": self.received_date.isoformat() if self.received_date else None,
            "status": self.status,
            "subtotal": float(self.subtotal),
            "tax_amount": float(self.tax_amount),
            "shipping_cost": float(self.shipping_cost),
            "total_amount": float(self.total_amount),
            "notes": self.notes,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_items:
            data["items"] = [item.to_dict() for item in self.items]
        return data


class PurchaseOrderItem(db.Model):
    """Line items in a purchase order"""

    __tablename__ = "purchase_order_items"

    id = db.Column(db.Integer, primary_key=True)
    purchase_order_id = db.Column(
        db.Integer,
        db.ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    part_id = db.Column(
        db.Integer,
        db.ForeignKey("parts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    quantity = db.Column(db.Integer, nullable=False)
    received_quantity = db.Column(db.Integer, default=0)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    discount_percent = db.Column(db.Numeric(5, 2), default=0)
    discount_amount = db.Column(db.Numeric(10, 2), default=0)
    tax_percent = db.Column(db.Numeric(5, 2), default=0)
    tax_amount = db.Column(db.Numeric(10, 2), default=0)
    line_total = db.Column(db.Numeric(10, 2), nullable=False)
    notes = db.Column(db.Text)

    part = db.relationship("Part", back_populates="purchase_items")

    @property
    def subtotal(self) -> float:
        return float(self.unit_price) * self.quantity

    @property
    def pending_quantity(self) -> int:
        return self.quantity - self.received_quantity

    @property
    def is_fully_received(self) -> bool:
        return self.received_quantity >= self.quantity

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "purchase_order_id": self.purchase_order_id,
            "part_id": self.part_id,
            "part_name": self.part.name if self.part else None,
            "part_sku": self.part.sku if self.part else None,
            "quantity": self.quantity,
            "received_quantity": self.received_quantity,
            "pending_quantity": self.pending_quantity,
            "unit_price": float(self.unit_price),
            "discount_percent": float(self.discount_percent),
            "discount_amount": float(self.discount_amount),
            "tax_percent": float(self.tax_percent),
            "tax_amount": float(self.tax_amount),
            "line_total": float(self.line_total),
            "notes": self.notes,
            "is_fully_received": self.is_fully_received,
        }


class Expense(db.Model):
    """Business expenses"""

    __tablename__ = "expenses"

    id = db.Column(db.Integer, primary_key=True)
    expense_date = db.Column(db.DateTime, default=now_utc, nullable=False, index=True)
    category = db.Column(
        db.String(50), nullable=False, index=True
    )  # rent, utilities, supplies, maintenance, marketing, other
    description = db.Column(db.Text, nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    tax_amount = db.Column(db.Numeric(10, 2), default=0)
    payment_method = db.Column(db.String(20), nullable=False)  # cash, card, bank_transfer
    receipt_number = db.Column(db.String(100))
    vendor = db.Column(db.String(100))
    is_recurring = db.Column(db.Boolean, default=False)
    recurring_frequency = db.Column(db.String(20))  # monthly, quarterly, yearly
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey("staff.id"))
    created_at = db.Column(db.DateTime, default=now_utc, nullable=False)
    updated_at = db.Column(db.DateTime, default=now_utc, onupdate=now_utc)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "expense_date": self.expense_date.isoformat() if self.expense_date else None,
            "category": self.category,
            "description": self.description,
            "amount": float(self.amount),
            "tax_amount": float(self.tax_amount),
            "payment_method": self.payment_method,
            "receipt_number": self.receipt_number,
            "vendor": self.vendor,
            "is_recurring": self.is_recurring,
            "recurring_frequency": self.recurring_frequency,
            "notes": self.notes,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class MaintenanceLog(db.Model):
    """Equipment/vehicle maintenance logs"""

    __tablename__ = "maintenance_logs"

    id = db.Column(db.Integer, primary_key=True)
    part_id = db.Column(db.Integer, db.ForeignKey("parts.id", ondelete="SET NULL"), index=True)
    equipment_name = db.Column(db.String(100), nullable=False)
    equipment_serial = db.Column(db.String(100))
    maintenance_date = db.Column(db.DateTime, default=now_utc, nullable=False, index=True)
    maintenance_type = db.Column(
        db.String(20), nullable=False, index=True
    )  # preventive, corrective, emergency, inspection
    description = db.Column(db.Text, nullable=False)
    cost = db.Column(db.Numeric(10, 2), default=0)
    performed_by = db.Column(db.String(100))  # Internal staff or external vendor
    vendor = db.Column(db.String(100))
    parts_used = db.Column(db.Text)  # JSON or comma-separated
    next_maintenance = db.Column(db.DateTime, index=True)
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey("staff.id"))
    created_at = db.Column(db.DateTime, default=now_utc, nullable=False)
    updated_at = db.Column(db.DateTime, default=now_utc, onupdate=now_utc)

    @property
    def is_overdue(self) -> bool:
        if self.next_maintenance:
            return now_utc() > self.next_maintenance
        return False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "part_id": self.part_id,
            "part_name": self.part.name if self.part else None,
            "equipment_name": self.equipment_name,
            "equipment_serial": self.equipment_serial,
            "maintenance_date": (
                self.maintenance_date.isoformat() if self.maintenance_date else None
            ),
            "maintenance_type": self.maintenance_type,
            "description": self.description,
            "cost": float(self.cost),
            "performed_by": self.performed_by,
            "vendor": self.vendor,
            "parts_used": self.parts_used,
            "next_maintenance": (
                self.next_maintenance.isoformat() if self.next_maintenance else None
            ),
            "is_overdue": self.is_overdue,
            "notes": self.notes,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
