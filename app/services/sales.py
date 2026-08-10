"""
Sales service - business logic for sales and customers.

Every public method takes/returns plain data or model instances and raises
``ValueError`` for business-rule violations; the API layer maps that to a 400.
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy import func, or_
from sqlalchemy.exc import SQLAlchemyError

from app.core.extensions import db
from app.core.time_utils import now_utc
from app.models import Customer, Part, Payment, Sale, SaleDetail, StockEntry

CENTS = Decimal("0.01")


def _money(value) -> Decimal:
    """Coerce to a 2dp Decimal without going through binary float."""
    if isinstance(value, Decimal):
        return value.quantize(CENTS)
    return Decimal(str(value or 0)).quantize(CENTS)


class CustomerService:
    """Service layer for customer operations"""

    @staticmethod
    def get_customers(
        page: int = 1, per_page: int = 20, search: str = None, active_only: bool = True
    ) -> Tuple[List[Customer], int]:
        query = Customer.query

        if active_only:
            query = query.filter(Customer.is_active.is_(True))

        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(
                    Customer.name.ilike(search_term),
                    Customer.email.ilike(search_term),
                    Customer.phone.ilike(search_term),
                )
            )

        query = query.order_by(Customer.name)
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        CustomerService._attach_stats(pagination.items)
        return pagination.items, pagination.total

    @staticmethod
    def _attach_stats(customers: List[Customer]) -> None:
        """Load order counts and lifetime spend for a page of customers.

        One grouped query for the whole page. Reading ``total_spent`` and
        ``total_orders`` off each instance otherwise costs two queries per
        row, which is what made the customers list scale linearly in queries.
        """
        if not customers:
            return

        ids = [c.id for c in customers]
        rows = (
            db.session.query(
                Sale.customer_id,
                func.count(Sale.id).label("orders"),
                func.coalesce(func.sum(Sale.total_amount), 0).label("spent"),
            )
            .filter(
                Sale.customer_id.in_(ids),
                Sale.payment_status != "refunded",
            )
            .group_by(Sale.customer_id)
            .all()
        )

        stats = {
            row.customer_id: {
                "total_orders": int(row.orders or 0),
                "total_spent": float(row.spent or 0),
            }
            for row in rows
        }

        for customer in customers:
            customer._stats = stats.get(customer.id, {"total_orders": 0, "total_spent": 0.0})

    @staticmethod
    def get_customer(customer_id: int) -> Optional[Customer]:
        return db.session.get(Customer, customer_id)

    @staticmethod
    def create_customer(data: dict) -> Customer:
        email = data.get("email")
        if email and Customer.query.filter(Customer.email == email).first():
            raise ValueError("A customer with that email already exists")

        customer = Customer(**data)
        db.session.add(customer)
        db.session.commit()
        return customer

    @staticmethod
    def update_customer(customer_id: int, data: dict) -> Optional[Customer]:
        customer = db.session.get(Customer, customer_id)
        if not customer:
            return None

        email = data.get("email")
        if email and email != customer.email:
            clash = Customer.query.filter(
                Customer.email == email, Customer.id != customer_id
            ).first()
            if clash:
                raise ValueError("A customer with that email already exists")

        for key, value in data.items():
            if hasattr(customer, key) and key not in ("id", "created_at", "updated_at"):
                setattr(customer, key, value)

        db.session.commit()
        return customer

    @staticmethod
    def delete_customer(customer_id: int) -> bool:
        """Deactivate a customer that has sales history, hard-delete otherwise."""
        customer = db.session.get(Customer, customer_id)
        if not customer:
            return False

        if customer.sales.count() > 0:
            customer.is_active = False
        else:
            db.session.delete(customer)

        db.session.commit()
        return True


class SalesService:
    """Service layer for sales operations"""

    @staticmethod
    def get_sales(
        page: int = 1,
        per_page: int = 20,
        start_date: datetime = None,
        end_date: datetime = None,
        staff_id: int = None,
        customer_id: int = None,
        payment_status: str = None,
    ) -> Tuple[List[Sale], int]:
        query = Sale.query

        if start_date:
            query = query.filter(Sale.sale_date >= start_date)
        if end_date:
            query = query.filter(Sale.sale_date <= end_date)
        if staff_id:
            query = query.filter(Sale.staff_id == staff_id)
        if customer_id:
            query = query.filter(Sale.customer_id == customer_id)
        if payment_status:
            query = query.filter(Sale.payment_status == payment_status)

        query = query.order_by(Sale.sale_date.desc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        return pagination.items, pagination.total

    @staticmethod
    def get_sale(sale_id: int) -> Optional[Sale]:
        return db.session.get(Sale, sale_id)

    @staticmethod
    def create_sale(data: dict, staff_id: int) -> Sale:
        """Create a sale, deduct stock, and record the stock movements.

        The whole thing is one transaction: if any line fails validation the
        sale is rolled back entirely, so stock is never partially deducted.

        Each line falls back to the part's catalogue price when the client
        omits ``unit_price``, but a POS operator *may* supply their own unit
        price and discount/tax percentages (SaleLineSchema accepts them) for a
        negotiated sale. What the client can never set is the sale total itself
        - total_amount, tax_amount and discount_amount are derived here from the
        line items, never taken from the request.
        """
        details_data = data.pop("details", None) or []
        if not details_data:
            raise ValueError("Sale must have at least one item")

        customer_id = data.get("customer_id")
        if customer_id and not db.session.get(Customer, customer_id):
            raise ValueError(f"Customer {customer_id} not found")

        try:
            sale = Sale(
                staff_id=staff_id,
                receipt_number=Sale.generate_receipt_number(),
                sale_date=data.get("sale_date") or now_utc(),
                payment_method=data["payment_method"],
                payment_status=data.get("payment_status", "paid"),
                customer_id=customer_id,
                notes=data.get("notes"),
                # Real values are computed below; seed the NOT NULL columns so
                # the flush that assigns sale.id cannot fail.
                total_amount=Decimal("0"),
                tax_amount=Decimal("0"),
                discount_amount=Decimal("0"),
            )
            db.session.add(sale)
            db.session.flush()

            subtotal = Decimal("0")
            tax_total = Decimal("0")
            discount_total = Decimal("0")

            for line in details_data:
                part_id = line["part_id"]
                quantity = int(line["quantity"])

                if quantity <= 0:
                    raise ValueError("Quantity must be at least 1")

                # Lock the row for the rest of the transaction so two
                # concurrent sales cannot both pass the stock check and
                # oversell. (No-op on SQLite, which serialises writes anyway.)
                part = (
                    db.session.query(Part)
                    .filter(Part.id == part_id)
                    .with_for_update()
                    .one_or_none()
                )
                if not part:
                    raise ValueError(f"Part {part_id} not found")
                if not part.is_active:
                    raise ValueError(f'Part "{part.name}" is not active')
                if part.stock_quantity < quantity:
                    raise ValueError(
                        f'Insufficient stock for "{part.name}" '
                        f"(requested {quantity}, available {part.stock_quantity})"
                    )

                # Fall back to the catalogue price when the client omits one.
                unit_price = line.get("unit_price")
                unit_price = _money(part.price if unit_price is None else unit_price)

                line_subtotal = _money(unit_price * quantity)
                discount_percent = _money(line.get("discount_percent", 0))
                discount_amount = _money(line_subtotal * discount_percent / 100)
                taxable_amount = line_subtotal - discount_amount
                tax_percent = _money(line.get("tax_percent", 0))
                tax_amount = _money(taxable_amount * tax_percent / 100)
                line_total = taxable_amount + tax_amount

                db.session.add(
                    SaleDetail(
                        sale_id=sale.id,
                        part_id=part_id,
                        quantity=quantity,
                        unit_price=unit_price,
                        # Snapshot the cost now so margin reporting stays correct
                        # even after the part's cost price is later revised.
                        unit_cost=_money(part.cost_price or 0),
                        discount_percent=discount_percent,
                        discount_amount=discount_amount,
                        tax_percent=tax_percent,
                        tax_amount=tax_amount,
                        line_total=line_total,
                    )
                )

                part.stock_quantity -= quantity

                db.session.add(
                    StockEntry(
                        part_id=part.id,
                        quantity=-quantity,
                        movement_type="sale",
                        reference_type="sale",
                        reference_id=sale.id,
                        notes=f"Sale {sale.receipt_number}",
                        created_by=staff_id,
                    )
                )

                subtotal += line_subtotal
                discount_total += discount_amount
                tax_total += tax_amount

            # `subtotal` and `item_count` are read-only properties on Sale,
            # derived from the line items - only the stored columns are set.
            sale.discount_amount = discount_total
            sale.tax_amount = tax_total
            sale.total_amount = subtotal - discount_total + tax_total

            # Alert on the parts this sale just depleted (added to the same
            # transaction, so a rollback discards the notifications too).
            from app.services.inventory import InventoryService

            InventoryService.notify_low_stock([detail["part_id"] for detail in details_data])

            db.session.commit()
        except (SQLAlchemyError, ValueError):
            db.session.rollback()
            raise

        return sale

    @staticmethod
    def get_amount_paid(sale: Sale) -> Decimal:
        """Total recorded against a sale across all payment rows."""
        total = (
            db.session.query(func.coalesce(func.sum(Payment.amount), 0))
            .filter(Payment.sale_id == sale.id)
            .scalar()
        )
        return _money(total)

    @staticmethod
    def process_payment(
        sale_id: int,
        amount,
        payment_method: str,
        reference_number: str = None,
        notes: str = None,
        user_id: int = None,
    ) -> Payment:
        """Record a payment against a sale and refresh its payment status."""
        sale = db.session.get(Sale, sale_id)
        if not sale:
            raise ValueError("Sale not found")

        if sale.payment_status == "refunded":
            raise ValueError("Cannot add a payment to a voided sale")

        amount = _money(amount)
        if amount <= 0:
            raise ValueError("Payment amount must be greater than zero")

        already_paid = SalesService.get_amount_paid(sale)
        outstanding = _money(sale.total_amount) - already_paid
        if amount > outstanding:
            raise ValueError(
                f"Payment of {amount} exceeds the outstanding balance of {outstanding}"
            )

        try:
            payment = Payment(
                sale_id=sale.id,
                amount=amount,
                payment_method=payment_method,
                reference_number=reference_number,
                notes=notes,
                created_by=user_id,
            )
            db.session.add(payment)

            total_paid = already_paid + amount
            if total_paid >= _money(sale.total_amount):
                sale.payment_status = "paid"
            elif total_paid > 0:
                sale.payment_status = "partial"
            else:
                sale.payment_status = "pending"

            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise

        return payment

    @staticmethod
    def void_sale(sale_id: int, user_id: int, reason: str) -> bool:
        """Void a sale and return its items to stock."""
        sale = db.session.get(Sale, sale_id)
        if not sale:
            return False

        if sale.payment_status == "refunded":
            return False  # Already voided

        try:
            for detail in sale.details:
                part = (
                    db.session.query(Part)
                    .filter(Part.id == detail.part_id)
                    .with_for_update()
                    .one_or_none()
                )
                if not part:
                    continue

                part.stock_quantity += detail.quantity
                db.session.add(
                    StockEntry(
                        part_id=part.id,
                        quantity=detail.quantity,
                        movement_type="return",
                        reference_type="sale",
                        reference_id=sale.id,
                        notes=f"Sale {sale.receipt_number} voided: {reason}",
                        created_by=user_id,
                    )
                )

            sale.payment_status = "refunded"
            voided_note = f"[{now_utc():%Y-%m-%d %H:%M} UTC] " f"Voided by user {user_id}: {reason}"
            sale.notes = f"{sale.notes}\n{voided_note}" if sale.notes else voided_note

            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise

        return True

    @staticmethod
    def get_sales_summary(start_date: datetime = None, end_date: datetime = None) -> dict:
        """Sales totals for a period, excluding voided sales."""
        query = db.session.query(
            func.count(Sale.id).label("total_sales"),
            func.coalesce(func.sum(Sale.total_amount), 0).label("total_revenue"),
            func.coalesce(func.sum(Sale.tax_amount), 0).label("total_tax"),
            func.coalesce(func.sum(Sale.discount_amount), 0).label("total_discount"),
            func.coalesce(func.avg(Sale.total_amount), 0).label("avg_sale"),
        ).filter(Sale.payment_status != "refunded")

        if start_date:
            query = query.filter(Sale.sale_date >= start_date)
        if end_date:
            query = query.filter(Sale.sale_date <= end_date)

        result = query.one()

        return {
            "total_sales": result.total_sales or 0,
            "total_revenue": float(result.total_revenue or 0),
            "total_tax": float(result.total_tax or 0),
            "total_discount": float(result.total_discount or 0),
            "avg_sale": float(result.avg_sale or 0),
        }

    @staticmethod
    def get_top_selling_parts(
        limit: int = 10, start_date: datetime = None, end_date: datetime = None
    ) -> List[dict]:
        """Best sellers by units sold, excluding voided sales."""
        query = (
            db.session.query(
                Part.id,
                Part.name,
                Part.sku,
                Part.brand,
                func.sum(SaleDetail.quantity).label("total_sold"),
                func.sum(SaleDetail.line_total).label("total_revenue"),
            )
            .join(SaleDetail, SaleDetail.part_id == Part.id)
            .join(Sale, Sale.id == SaleDetail.sale_id)
        )

        if start_date:
            query = query.filter(Sale.sale_date >= start_date)
        if end_date:
            query = query.filter(Sale.sale_date <= end_date)

        query = query.filter(Sale.payment_status != "refunded")
        query = query.group_by(Part.id, Part.name, Part.sku, Part.brand)
        query = query.order_by(func.sum(SaleDetail.quantity).desc())
        query = query.limit(max(1, min(limit, 100)))

        return [
            {
                "part_id": r.id,
                "name": r.name,
                "sku": r.sku,
                "brand": r.brand,
                "total_sold": int(r.total_sold or 0),
                "total_revenue": float(r.total_revenue or 0),
            }
            for r in query.all()
        ]
