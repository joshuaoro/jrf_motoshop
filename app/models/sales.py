"""
Database models - Sales, Customers, Transactions
"""

import uuid
from typing import ClassVar

from app.core.extensions import db
from app.core.time_utils import now_utc


class Customer(db.Model):
    """Customers"""

    __tablename__ = "customers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    email = db.Column(db.String(100), unique=True, index=True, nullable=True)
    phone = db.Column(db.String(20), index=True)
    address = db.Column(db.Text)
    city = db.Column(db.String(50))
    postal_code = db.Column(db.String(20))
    tax_id = db.Column(db.String(50))  # For B2B customers
    credit_limit = db.Column(db.Numeric(10, 2), default=0)
    balance = db.Column(db.Numeric(10, 2), default=0)  # Running balance
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=now_utc, nullable=False)
    updated_at = db.Column(db.DateTime, default=now_utc, onupdate=now_utc)

    # Relationships
    sales = db.relationship("Sale", backref="customer", lazy="dynamic")

    # Populated in bulk by CustomerService.get_customers so that rendering a
    # page of customers does not run two queries per row. Falls back to a
    # per-instance query when absent (single-record views, tests).
    # ClassVar keeps the declarative mapper from treating it as a column.
    _stats: ClassVar[dict | None] = None

    @property
    def total_spent(self) -> float:
        if self._stats is not None:
            return self._stats["total_spent"]
        from sqlalchemy import func

        from app.core.extensions import db

        total = (
            db.session.query(func.coalesce(func.sum(Sale.total_amount), 0))
            .filter(
                Sale.customer_id == self.id,
                Sale.payment_status != "refunded",
            )
            .scalar()
        )
        return float(total or 0)

    @property
    def total_orders(self) -> int:
        if self._stats is not None:
            return self._stats["total_orders"]
        return self.sales.count()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "address": self.address,
            "city": self.city,
            "postal_code": self.postal_code,
            "tax_id": self.tax_id,
            "credit_limit": float(self.credit_limit),
            "balance": float(self.balance),
            "is_active": self.is_active,
            "total_spent": self.total_spent,
            "total_orders": self.total_orders,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<Customer {self.name}>"


class Sale(db.Model):
    """Sales transactions"""

    __tablename__ = "sales"

    id = db.Column(db.Integer, primary_key=True)
    sale_date = db.Column(db.DateTime, default=now_utc, nullable=False, index=True)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    tax_amount = db.Column(db.Numeric(10, 2), default=0)
    discount_amount = db.Column(db.Numeric(10, 2), default=0)
    payment_method = db.Column(
        db.String(20), nullable=False, index=True
    )  # cash, card, gcash, bank_transfer
    payment_status = db.Column(
        db.String(20), default="paid", index=True
    )  # paid, partial, pending, refunded
    staff_id = db.Column(db.Integer, db.ForeignKey("staff.id"), nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), index=True)
    receipt_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=now_utc, nullable=False)
    updated_at = db.Column(db.DateTime, default=now_utc, onupdate=now_utc)

    # Relationships
    details = db.relationship(
        # selectin rather than dynamic: serialising a page of sales renders
        # every sale's lines, which cost one query each under a dynamic
        # relationship. selectin fetches them all in a single follow-up query.
        "SaleDetail",
        backref="sale",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    payments = db.relationship(
        "Payment", backref="sale", lazy="dynamic", cascade="all, delete-orphan"
    )

    @staticmethod
    def generate_receipt_number() -> str:
        return f"RCP-{now_utc().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

    @property
    def subtotal(self) -> float:
        return sum(float(d.line_total) for d in self.details)

    @property
    def item_count(self) -> int:
        return sum(d.quantity for d in self.details)

    def to_dict(self, include_details: bool = False) -> dict:
        data = {
            "id": self.id,
            "sale_date": self.sale_date.isoformat() if self.sale_date else None,
            "total_amount": float(self.total_amount),
            "tax_amount": float(self.tax_amount),
            "discount_amount": float(self.discount_amount),
            "payment_method": self.payment_method,
            "payment_status": self.payment_status,
            "staff_id": self.staff_id,
            "customer_id": self.customer_id,
            "receipt_number": self.receipt_number,
            "notes": self.notes,
            "subtotal": self.subtotal,
            "item_count": self.item_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_details:
            data["details"] = [d.to_dict() for d in self.details]
        return data

    def __repr__(self):
        return f"<Sale {self.receipt_number}: {self.total_amount}>"


class SaleDetail(db.Model):
    """Line items in a sale"""

    __tablename__ = "sale_details"

    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id", ondelete="CASCADE"), primary_key=True)
    part_id = db.Column(
        db.Integer, db.ForeignKey("parts.id", ondelete="RESTRICT"), primary_key=True
    )
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)  # Price at time of sale
    # Cost snapshot taken when the sale is made. Stored rather than read back
    # from Part.cost_price so that later price changes cannot retroactively
    # rewrite the margin on sales that already happened.
    unit_cost = db.Column(db.Numeric(10, 2), default=0, nullable=False)
    discount_percent = db.Column(db.Numeric(5, 2), default=0)
    discount_amount = db.Column(db.Numeric(10, 2), default=0)
    tax_percent = db.Column(db.Numeric(5, 2), default=0)
    tax_amount = db.Column(db.Numeric(10, 2), default=0)
    line_total = db.Column(db.Numeric(10, 2), nullable=False)  # Final line total

    # Relationships
    part = db.relationship("Part", back_populates="sale_details")

    @property
    def subtotal(self) -> float:
        return float(self.unit_price) * self.quantity

    @property
    def line_cost(self) -> float:
        """Cost of goods sold for this line."""
        return float(self.unit_cost or 0) * self.quantity

    @property
    def line_profit(self) -> float:
        return float(self.line_total or 0) - self.line_cost

    def to_dict(self) -> dict:
        return {
            "sale_id": self.sale_id,
            "part_id": self.part_id,
            "part_name": self.part.name if self.part else None,
            "part_sku": self.part.sku if self.part else None,
            "quantity": self.quantity,
            "unit_price": float(self.unit_price),
            "unit_cost": float(self.unit_cost or 0),
            "line_cost": self.line_cost,
            "line_profit": self.line_profit,
            "discount_percent": float(self.discount_percent),
            "discount_amount": float(self.discount_amount),
            "tax_percent": float(self.tax_percent),
            "tax_amount": float(self.tax_amount),
            "line_total": float(self.line_total),
        }

    def __repr__(self):
        return f"<SaleDetail sale:{self.sale_id} part:{self.part_id} qty:{self.quantity}>"


class Payment(db.Model):
    """Payment records for sales (partial payments, refunds)"""

    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(
        db.Integer,
        db.ForeignKey("sales.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_method = db.Column(db.String(20), nullable=False)
    payment_date = db.Column(db.DateTime, default=now_utc, nullable=False)
    reference_number = db.Column(db.String(100))
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey("staff.id"))
    created_at = db.Column(db.DateTime, default=now_utc, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "sale_id": self.sale_id,
            "amount": float(self.amount),
            "payment_method": self.payment_method,
            "payment_date": self.payment_date.isoformat() if self.payment_date else None,
            "reference_number": self.reference_number,
            "notes": self.notes,
        }
