"""
Operations services - expenses, purchase orders and maintenance logs.

These three models shipped with the schema but had nothing driving them: the
expenses report could only ever return zeros, and purchase orders existed only
as a foreign key that supplier deletion checked. This module supplies the
business logic; the matching blueprints live in ``app/api/``.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload, selectinload

from app.core.extensions import db
from app.core.time_utils import now_utc
from app.models import (
    Expense,
    MaintenanceLog,
    Part,
    PurchaseOrder,
    PurchaseOrderItem,
    StockEntry,
    Supplier,
)

CENTS = Decimal("0.01")

# A purchase order may only move forward through these states.
PO_TRANSITIONS = {
    "pending": {"ordered", "cancelled"},
    "ordered": {"partial", "received", "cancelled"},
    "partial": {"received", "cancelled"},
    "received": set(),
    "cancelled": set(),
}


def _money(value) -> Decimal:
    if isinstance(value, Decimal):
        return value.quantize(CENTS)
    return Decimal(str(value or 0)).quantize(CENTS)


class ExpenseService:
    """Business expenses."""

    @staticmethod
    def get_expenses(
        page: int = 1,
        per_page: int = 20,
        category: str = None,
        start_date: datetime = None,
        end_date: datetime = None,
        search: str = None,
    ) -> Tuple[List[Expense], int]:
        query = Expense.query

        if category:
            query = query.filter(Expense.category == category)
        if start_date:
            query = query.filter(Expense.expense_date >= start_date)
        if end_date:
            query = query.filter(Expense.expense_date <= end_date)
        if search:
            term = f"%{search}%"
            query = query.filter(
                or_(
                    Expense.description.ilike(term),
                    Expense.vendor.ilike(term),
                    Expense.receipt_number.ilike(term),
                )
            )

        pagination = query.order_by(Expense.expense_date.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        return pagination.items, pagination.total

    @staticmethod
    def get_expense(expense_id: int) -> Optional[Expense]:
        return db.session.get(Expense, expense_id)

    @staticmethod
    def create_expense(data: dict, user_id: int) -> Expense:
        data = dict(data)
        data.setdefault("expense_date", now_utc())

        try:
            expense = Expense(created_by=user_id, **data)
            db.session.add(expense)
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise

        return expense

    @staticmethod
    def update_expense(expense_id: int, data: dict) -> Optional[Expense]:
        expense = db.session.get(Expense, expense_id)
        if not expense:
            return None

        try:
            for key, value in data.items():
                if hasattr(expense, key) and key not in (
                    "id",
                    "created_at",
                    "updated_at",
                    "created_by",
                ):
                    setattr(expense, key, value)
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise

        return expense

    @staticmethod
    def delete_expense(expense_id: int) -> bool:
        expense = db.session.get(Expense, expense_id)
        if not expense:
            return False

        try:
            db.session.delete(expense)
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise

        return True


class PurchaseOrderService:
    """Purchase orders and goods receipt."""

    @staticmethod
    def get_orders(
        page: int = 1,
        per_page: int = 20,
        supplier_id: int = None,
        status: str = None,
    ) -> Tuple[List[PurchaseOrder], int]:
        query = PurchaseOrder.query

        if supplier_id:
            query = query.filter(PurchaseOrder.supplier_id == supplier_id)
        if status:
            query = query.filter(PurchaseOrder.status == status)

        # to_dict() reads supplier.name for every row; without this join that
        # is one query per order.
        query = query.options(joinedload(PurchaseOrder.supplier))

        pagination = query.order_by(PurchaseOrder.order_date.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        return pagination.items, pagination.total

    @staticmethod
    def get_order(order_id: int) -> Optional[PurchaseOrder]:
        return (
            db.session.query(PurchaseOrder)
            .options(selectinload(PurchaseOrder.items).selectinload(PurchaseOrderItem.part))
            .filter(PurchaseOrder.id == order_id)
            .one_or_none()
        )

    @staticmethod
    def create_order(data: dict, user_id: int) -> PurchaseOrder:
        """Create a purchase order and compute its totals from the line items.

        Totals are derived here, never taken from the request, for the same
        reason sale totals are.
        """
        items_data = data.pop("items", None) or []
        if not items_data:
            raise ValueError("Purchase order must have at least one item")

        supplier = db.session.get(Supplier, data.get("supplier_id"))
        if not supplier:
            raise ValueError(f"Supplier {data.get('supplier_id')} not found")

        part_ids = [item["part_id"] for item in items_data]
        if len(set(part_ids)) != len(part_ids):
            raise ValueError("Each part may only appear once per purchase order")

        try:
            order = PurchaseOrder(
                order_number=PurchaseOrder.generate_order_number(),
                supplier_id=supplier.id,
                expected_date=data.get("expected_date"),
                status=data.get("status", "pending"),
                shipping_cost=_money(data.get("shipping_cost", 0)),
                notes=data.get("notes"),
                created_by=user_id,
                subtotal=Decimal("0"),
                tax_amount=Decimal("0"),
                total_amount=Decimal("0"),
            )
            db.session.add(order)
            db.session.flush()

            subtotal = Decimal("0")
            tax_total = Decimal("0")

            for line in items_data:
                part = db.session.get(Part, line["part_id"])
                if not part:
                    raise ValueError(f"Part {line['part_id']} not found")

                quantity = int(line["quantity"])
                if quantity <= 0:
                    raise ValueError("Quantity must be at least 1")

                unit_price = _money(line["unit_price"])
                line_subtotal = _money(unit_price * quantity)
                discount_percent = _money(line.get("discount_percent", 0))
                discount_amount = _money(line_subtotal * discount_percent / 100)
                taxable = line_subtotal - discount_amount
                tax_percent = _money(line.get("tax_percent", 0))
                tax_amount = _money(taxable * tax_percent / 100)

                db.session.add(
                    PurchaseOrderItem(
                        purchase_order_id=order.id,
                        part_id=part.id,
                        quantity=quantity,
                        unit_price=unit_price,
                        discount_percent=discount_percent,
                        discount_amount=discount_amount,
                        tax_percent=tax_percent,
                        tax_amount=tax_amount,
                        line_total=taxable + tax_amount,
                        notes=line.get("notes"),
                    )
                )

                subtotal += line_subtotal - discount_amount
                tax_total += tax_amount

            order.subtotal = subtotal
            order.tax_amount = tax_total
            order.total_amount = subtotal + tax_total + order.shipping_cost

            db.session.commit()
        except (SQLAlchemyError, ValueError):
            db.session.rollback()
            raise

        return order

    @staticmethod
    def next_statuses(status: str) -> set:
        """Statuses an order in ``status`` may legally move to."""
        return PO_TRANSITIONS.get(status, set())

    @staticmethod
    def set_status(order_id: int, status: str) -> Optional[PurchaseOrder]:
        """Move an order to a new status, rejecting invalid transitions."""
        order = db.session.get(PurchaseOrder, order_id)
        if not order:
            return None

        if status == order.status:
            return order

        allowed = PO_TRANSITIONS.get(order.status, set())
        if status not in allowed:
            raise ValueError(
                f'Cannot change status from "{order.status}" to "{status}". '
                f"Allowed: {', '.join(sorted(allowed)) or 'none'}"
            )

        try:
            order.status = status
            if status == "cancelled":
                order.received_date = None
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise

        return order

    @staticmethod
    def receive_items(order_id: int, receipts: List[dict], user_id: int) -> PurchaseOrder:
        """Book goods in against a purchase order.

        Increments stock, records a StockEntry per line, and refreshes the
        part's cost price from what was actually paid so margin reporting
        tracks real costs. The order becomes 'partial' or 'received'
        automatically depending on what is still outstanding.
        """
        order = db.session.get(PurchaseOrder, order_id)
        if not order:
            raise ValueError("Purchase order not found")

        if order.status in ("cancelled", "received"):
            raise ValueError(f"Cannot receive against a {order.status} purchase order")

        if not receipts:
            raise ValueError("Nothing to receive")

        items = {item.part_id: item for item in order.items}

        try:
            for receipt in receipts:
                part_id = receipt["part_id"]
                quantity = int(receipt["quantity"])

                item = items.get(part_id)
                if item is None:
                    raise ValueError(f"Part {part_id} is not on this purchase order")
                if quantity <= 0:
                    raise ValueError("Received quantity must be at least 1")

                outstanding = item.quantity - item.received_quantity
                if quantity > outstanding:
                    raise ValueError(
                        f'Cannot receive {quantity} of "{item.part.name}": '
                        f"only {outstanding} outstanding"
                    )

                part = db.session.query(Part).filter(Part.id == part_id).with_for_update().one()

                item.received_quantity += quantity
                part.stock_quantity += quantity
                # Last-cost valuation: the newest purchase price becomes the
                # part's cost. Simple and predictable; a weighted average
                # would need a separate cost-layer table.
                part.cost_price = item.unit_price

                db.session.add(
                    StockEntry(
                        part_id=part.id,
                        quantity=quantity,
                        movement_type="purchase",
                        reference_type="purchase_order",
                        reference_id=order.id,
                        notes=f"Received against {order.order_number}",
                        created_by=user_id,
                    )
                )

            fully_received = all(item.is_fully_received for item in order.items)
            order.status = "received" if fully_received else "partial"
            order.received_date = now_utc() if fully_received else None

            db.session.commit()
        except (SQLAlchemyError, ValueError):
            db.session.rollback()
            raise

        return order

    @staticmethod
    def delete_order(order_id: int) -> bool:
        """Delete an order that has never had stock booked against it."""
        order = db.session.get(PurchaseOrder, order_id)
        if not order:
            return False

        if any(item.received_quantity > 0 for item in order.items):
            raise ValueError(
                "Cannot delete a purchase order with received stock; cancel it instead"
            )

        try:
            db.session.delete(order)
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise

        return True


class MaintenanceService:
    """Equipment maintenance logs."""

    @staticmethod
    def get_logs(
        page: int = 1,
        per_page: int = 20,
        maintenance_type: str = None,
        overdue_only: bool = False,
    ) -> Tuple[List[MaintenanceLog], int]:
        query = MaintenanceLog.query

        if maintenance_type:
            query = query.filter(MaintenanceLog.maintenance_type == maintenance_type)
        if overdue_only:
            query = query.filter(
                MaintenanceLog.next_maintenance.isnot(None),
                MaintenanceLog.next_maintenance < now_utc(),
            )

        pagination = query.order_by(MaintenanceLog.maintenance_date.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        return pagination.items, pagination.total

    @staticmethod
    def get_log(log_id: int) -> Optional[MaintenanceLog]:
        return db.session.get(MaintenanceLog, log_id)

    @staticmethod
    def get_summary() -> dict:
        """Counts for the maintenance page header."""
        from sqlalchemy import func as sa_func

        now = now_utc()

        soon = now + timedelta(days=30)

        total = db.session.query(sa_func.count(MaintenanceLog.id)).scalar() or 0
        overdue = (
            db.session.query(sa_func.count(MaintenanceLog.id))
            .filter(
                MaintenanceLog.next_maintenance.isnot(None),
                MaintenanceLog.next_maintenance < now,
            )
            .scalar()
            or 0
        )
        upcoming = (
            db.session.query(sa_func.count(MaintenanceLog.id))
            .filter(
                MaintenanceLog.next_maintenance.isnot(None),
                MaintenanceLog.next_maintenance >= now,
                MaintenanceLog.next_maintenance <= soon,
            )
            .scalar()
            or 0
        )
        spend = (
            db.session.query(sa_func.coalesce(sa_func.sum(MaintenanceLog.cost), 0))
            .filter(MaintenanceLog.maintenance_date >= now - timedelta(days=365))
            .scalar()
        )

        return {
            "total": total,
            "overdue": overdue,
            "upcoming": upcoming,
            "spend_12m": float(spend or 0),
        }

    @staticmethod
    def create_log(data: dict, user_id: int) -> MaintenanceLog:
        data = dict(data)
        data.setdefault("maintenance_date", now_utc())

        if data.get("part_id") and not db.session.get(Part, data["part_id"]):
            raise ValueError(f"Part {data['part_id']} not found")

        try:
            log = MaintenanceLog(created_by=user_id, **data)
            db.session.add(log)
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise

        return log

    @staticmethod
    def update_log(log_id: int, data: dict) -> Optional[MaintenanceLog]:
        log = db.session.get(MaintenanceLog, log_id)
        if not log:
            return None

        try:
            for key, value in data.items():
                if hasattr(log, key) and key not in (
                    "id",
                    "created_at",
                    "updated_at",
                    "created_by",
                ):
                    setattr(log, key, value)
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise

        return log

    @staticmethod
    def delete_log(log_id: int) -> bool:
        log = db.session.get(MaintenanceLog, log_id)
        if not log:
            return False

        try:
            db.session.delete(log)
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise

        return True
