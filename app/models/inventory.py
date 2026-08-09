"""
Database models - Inventory (Parts, Suppliers, Stock)
"""

from app.core.extensions import db
from datetime import datetime


class Part(db.Model):
    """Parts/Inventory items"""

    __tablename__ = "parts"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    description = db.Column(db.Text)
    part_type = db.Column(db.String(50), index=True)  # Engine, Brakes, Electrical, Body, etc.
    brand = db.Column(db.String(50), index=True)
    price = db.Column(db.Numeric(10, 2), nullable=False)  # Selling price
    # What the shop pays for the part. Required for any margin/profit figure;
    # without it a "profitability" report can only ever report zero.
    cost_price = db.Column(db.Numeric(10, 2), default=0, nullable=False)
    stock_quantity = db.Column(db.Integer, default=0, nullable=False, index=True)
    min_stock_level = db.Column(db.Integer, default=5)  # Reorder point
    sku = db.Column(db.String(50), unique=True, index=True)  # Auto-generated or manual
    barcode = db.Column(db.String(100), unique=True, index=True, nullable=True)
    location = db.Column(db.String(50))  # Shelf/bin location
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    stock_entries = db.relationship(
        "StockEntry", backref="part", lazy="dynamic", cascade="all, delete-orphan"
    )
    sale_details = db.relationship("SaleDetail", back_populates="part", lazy="dynamic")
    purchase_items = db.relationship("PurchaseOrderItem", back_populates="part", lazy="dynamic")
    maintenance_logs = db.relationship("MaintenanceLog", backref="part", lazy="dynamic")
    suppliers = db.relationship("Supplier", secondary="supplier_part", back_populates="parts")

    @property
    def stock_status(self) -> str:
        """Get stock status based on quantity.

        ``min_stock_level`` is the reorder point, so on-hand *at or below* it is
        already worth reordering - not merely below it. A part sitting exactly
        on the reorder point reads as ``low_stock`` rather than ``moderate``.
        """
        if self.stock_quantity <= 0:
            return "out_of_stock"
        elif self.stock_quantity <= self.min_stock_level:
            return "low_stock"
        elif self.stock_quantity <= self.min_stock_level * 2:
            return "moderate"
        return "in_stock"

    @property
    def is_low_stock(self) -> bool:
        return self.stock_quantity <= self.min_stock_level

    @property
    def stock_value(self) -> float:
        """Retail value of the stock on hand."""
        return float(self.price) * self.stock_quantity

    @property
    def stock_cost(self) -> float:
        """What the stock on hand cost to acquire."""
        return float(self.cost_price or 0) * self.stock_quantity

    @property
    def margin_percent(self) -> float:
        """Gross margin on a single unit, as a percentage of the sale price."""
        price = float(self.price or 0)
        if price <= 0:
            return 0.0
        return round((price - float(self.cost_price or 0)) / price * 100, 2)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "part_type": self.part_type,
            "brand": self.brand,
            "price": float(self.price),
            "cost_price": float(self.cost_price or 0),
            "margin_percent": self.margin_percent,
            "stock_quantity": self.stock_quantity,
            "min_stock_level": self.min_stock_level,
            "sku": self.sku,
            "barcode": self.barcode,
            "location": self.location,
            "is_active": self.is_active,
            "stock_status": self.stock_status,
            "stock_value": self.stock_value,
            "stock_cost": self.stock_cost,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "suppliers": [{"id": s.id, "name": s.name} for s in self.suppliers],
        }

    def __repr__(self):
        return f"<Part {self.name} ({self.stock_quantity} in stock)>"


class Supplier(db.Model):
    """Suppliers/Vendors"""

    __tablename__ = "suppliers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    contact_no = db.Column(db.String(20))
    email = db.Column(db.String(100))
    address = db.Column(db.Text)
    contact_person = db.Column(db.String(100))
    payment_terms = db.Column(db.String(50))  # Net 30, COD, etc.
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    parts = db.relationship("Part", secondary="supplier_part", back_populates="suppliers")
    purchase_orders = db.relationship("PurchaseOrder", backref="supplier", lazy="dynamic")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "contact_no": self.contact_no,
            "email": self.email,
            "address": self.address,
            "contact_person": self.contact_person,
            "payment_terms": self.payment_terms,
            "is_active": self.is_active,
            "parts_count": len(self.parts),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<Supplier {self.name}>"


# Association table for Part-Supplier many-to-many
supplier_part = db.Table(
    "supplier_part",
    db.Column(
        "supplier_id",
        db.Integer,
        db.ForeignKey("suppliers.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    db.Column(
        "part_id",
        db.Integer,
        db.ForeignKey("parts.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    db.Column("supplier_sku", db.String(50)),  # Supplier's SKU for this part
    db.Column("cost_price", db.Numeric(10, 2)),  # Supplier's price
    db.Column("lead_time_days", db.Integer),
    db.Column("is_preferred", db.Boolean, default=False),
    db.Column("created_at", db.DateTime, default=datetime.utcnow),
)


class StockEntry(db.Model):
    """Stock movement log"""

    __tablename__ = "stock_entries"

    id = db.Column(db.Integer, primary_key=True)
    entry_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False)  # Positive for in, negative for out
    movement_type = db.Column(
        db.String(20), nullable=False, index=True
    )  # sale, purchase, adjustment, return, transfer
    reference_type = db.Column(db.String(20))  # sale, purchase_order, adjustment
    reference_id = db.Column(db.Integer)  # ID of the reference document
    notes = db.Column(db.Text)
    part_id = db.Column(
        db.Integer,
        db.ForeignKey("parts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by = db.Column(db.Integer, db.ForeignKey("staff.id"))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "entry_date": self.entry_date.isoformat() if self.entry_date else None,
            "quantity": self.quantity,
            "movement_type": self.movement_type,
            "reference_type": self.reference_type,
            "reference_id": self.reference_id,
            "notes": self.notes,
            "part_id": self.part_id,
            "created_by": self.created_by,
        }

    def __repr__(self):
        return f"<StockEntry {self.part_id}: {self.quantity}>"
