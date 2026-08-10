"""
Inventory service - business logic for parts and suppliers
"""

from typing import List, Optional, Tuple
from sqlalchemy import func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload
from app.core.extensions import db
from app.models import Part, Supplier, StockEntry, supplier_part
from app.core.time_utils import now_utc
import uuid


class InventoryService:
    """Service layer for inventory operations"""

    @staticmethod
    def get_parts(
        page: int = 1,
        per_page: int = 20,
        search: str = None,
        part_type: str = None,
        brand: str = None,
        low_stock_only: bool = False,
        active_only: bool = True,
    ) -> Tuple[List[Part], int]:
        """Get paginated parts with filters"""
        query = Part.query

        if active_only:
            query = query.filter(Part.is_active.is_(True))

        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(
                    Part.name.ilike(search_term),
                    Part.sku.ilike(search_term),
                    Part.barcode.ilike(search_term),
                    Part.description.ilike(search_term),
                )
            )

        if part_type:
            query = query.filter(Part.part_type == part_type)

        if brand:
            query = query.filter(Part.brand == brand)

        if low_stock_only:
            query = query.filter(Part.stock_quantity <= Part.min_stock_level)

        # Order by name
        query = query.order_by(Part.name)

        # Every serialiser and template renders each part's suppliers, which
        # is one extra query per row without this. selectinload fetches them
        # all in a single follow-up query instead.
        query = query.options(selectinload(Part.suppliers))

        # Paginate
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        return pagination.items, pagination.total

    @staticmethod
    def get_part(part_id: int) -> Optional[Part]:
        """Get part by ID"""
        return db.session.get(Part, part_id)

    @staticmethod
    def _assert_unique(field: str, value, exclude_id: int = None) -> None:
        """Guard the unique columns before insert.

        Enforced here rather than in the API so the web forms, the API and the
        CLI seeders all get the same rule and the same message instead of a
        raw IntegrityError.
        """
        if not value:
            return
        query = Part.query.filter(getattr(Part, field) == value)
        if exclude_id is not None:
            query = query.filter(Part.id != exclude_id)
        if query.first():
            raise ValueError(f'{field.upper()} "{value}" is already in use')

    @staticmethod
    def create_part(data: dict, user_id: int) -> Part:
        """Create new part"""
        data = dict(data)

        # Generate SKU if not provided
        if not data.get("sku"):
            data["sku"] = f"PRT-{now_utc().strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}"

        InventoryService._assert_unique("sku", data.get("sku"))
        InventoryService._assert_unique("barcode", data.get("barcode"))

        supplier_ids = data.pop("supplier_ids", [])

        try:
            part = Part(**data)
            db.session.add(part)
            db.session.flush()  # Get ID

            if supplier_ids:
                part.suppliers = Supplier.query.filter(Supplier.id.in_(supplier_ids)).all()

            # Record the opening balance so stock history reconciles with the
            # current quantity from day one.
            if part.stock_quantity > 0:
                db.session.add(
                    StockEntry(
                        part_id=part.id,
                        quantity=part.stock_quantity,
                        movement_type="adjustment",
                        reference_type="initial",
                        notes="Initial stock on creation",
                        created_by=user_id,
                    )
                )

            db.session.commit()
        except (SQLAlchemyError, ValueError):
            db.session.rollback()
            raise

        return part

    @staticmethod
    def update_part(part_id: int, data: dict, user_id: int) -> Optional[Part]:
        """Update part"""
        part = db.session.get(Part, part_id)
        if not part:
            return None

        data = dict(data)

        if "sku" in data:
            InventoryService._assert_unique("sku", data["sku"], exclude_id=part_id)
        if "barcode" in data:
            InventoryService._assert_unique("barcode", data["barcode"], exclude_id=part_id)

        old_stock = part.stock_quantity
        supplier_ids = data.pop("supplier_ids", None)

        try:
            for key, value in data.items():
                if hasattr(part, key) and key not in ("id", "created_at", "updated_at"):
                    setattr(part, key, value)

            if supplier_ids is not None:
                part.suppliers = Supplier.query.filter(Supplier.id.in_(supplier_ids)).all()

            if part.stock_quantity != old_stock:
                db.session.add(
                    StockEntry(
                        part_id=part.id,
                        quantity=part.stock_quantity - old_stock,
                        movement_type="adjustment",
                        reference_type="manual",
                        notes=f"Stock adjusted from {old_stock} to {part.stock_quantity}",
                        created_by=user_id,
                    )
                )

            db.session.commit()
        except (SQLAlchemyError, ValueError):
            db.session.rollback()
            raise

        return part

    @staticmethod
    def delete_part(part_id: int) -> bool:
        """Deactivate a part with sales history, hard-delete an unused one."""
        part = db.session.get(Part, part_id)
        if not part:
            return False

        try:
            # A part referenced by a sale cannot be removed: SaleDetail.part_id
            # is ON DELETE RESTRICT, and the history must stay auditable.
            if part.sale_details.count() > 0 or part.purchase_items.count() > 0:
                part.is_active = False
            else:
                db.session.delete(part)

            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise

        return True

    @staticmethod
    def adjust_stock(
        part_id: int,
        quantity_change: int,
        movement_type: str,
        reference_type: str = None,
        reference_id: int = None,
        notes: str = None,
        user_id: int = None,
    ) -> Optional[Part]:
        """Adjust stock quantity and record the movement."""
        # Lock the row so two concurrent adjustments cannot both read the same
        # starting quantity and lose one of the updates.
        part = db.session.query(Part).filter(Part.id == part_id).with_for_update().one_or_none()
        if not part:
            return None

        new_stock = part.stock_quantity + quantity_change
        if new_stock < 0:
            db.session.rollback()
            raise ValueError(
                f"Insufficient stock: {part.stock_quantity} available, "
                f"cannot apply a change of {quantity_change}"
            )

        try:
            part.stock_quantity = new_stock
            db.session.add(
                StockEntry(
                    part_id=part.id,
                    quantity=quantity_change,
                    movement_type=movement_type,
                    reference_type=reference_type,
                    reference_id=reference_id,
                    notes=notes,
                    created_by=user_id,
                )
            )
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise

        return part

    @staticmethod
    def get_low_stock_parts(threshold: int = None) -> List[Part]:
        """Get active parts at or below the low-stock threshold."""
        if threshold is None:
            from app.services.system import SettingsService

            threshold = SettingsService.get_setting("inventory", "low_stock_threshold", 5)
            try:
                threshold = int(threshold)
            except (TypeError, ValueError):
                threshold = 5

        return (
            Part.query.filter(Part.is_active.is_(True), Part.stock_quantity <= threshold)
            .order_by(Part.stock_quantity.asc())
            .all()
        )

    @staticmethod
    def notify_low_stock(part_ids: List[int] = None) -> int:
        """Queue low-stock notifications for admins and managers.

        With ``part_ids`` the check is limited to those parts - used after a
        sale, so staff are told about what just moved rather than being sent a
        fresh copy of the entire low-stock list on every transaction. With
        ``None`` it sweeps the whole catalogue, which is what the nightly
        Celery task wants.

        Rows are added to the current session but NOT committed; the caller
        owns the transaction.

        Returns the number of low-stock parts found.
        """
        from app.models import Notification, User
        from app.services.system import SettingsService

        if part_ids is not None and not part_ids:
            return 0

        if not SettingsService.get_setting("inventory", "low_stock_alert", True):
            return 0

        threshold = SettingsService.get_setting("inventory", "low_stock_threshold", 5)
        try:
            threshold = int(threshold)
        except (TypeError, ValueError):
            threshold = 5

        query = Part.query.filter(
            Part.is_active.is_(True),
            Part.stock_quantity <= threshold,
        )
        if part_ids is not None:
            query = query.filter(Part.id.in_(part_ids))

        low_parts = query.order_by(Part.stock_quantity.asc()).all()
        if not low_parts:
            return 0

        names = ", ".join(p.name for p in low_parts[:5])
        if len(low_parts) > 5:
            names += f" and {len(low_parts) - 5} more"

        title = f"Low stock: {len(low_parts)} item(s) need reordering"
        message = f"Stock fell below {threshold} for: {names}"

        recipients = User.query.filter(
            User.role.in_(("admin", "manager")),
            User.is_active.is_(True),
        ).all()

        for user in recipients:
            db.session.add(
                Notification(
                    user_id=user.id,
                    title=title,
                    message=message,
                    type="warning",
                    category="inventory",
                    action_url="/inventory/?low_stock=true",
                    action_text="View Inventory",
                    priority=5,
                )
            )

        return len(low_parts)

    @staticmethod
    def get_part_types() -> List[str]:
        """Get all unique part types"""
        return [
            r[0]
            for r in db.session.query(Part.part_type)
            .distinct()
            .filter(Part.part_type.isnot(None))
            .all()
        ]

    @staticmethod
    def get_brands() -> List[str]:
        """Get all unique brands"""
        return [
            r[0]
            for r in db.session.query(Part.brand).distinct().filter(Part.brand.isnot(None)).all()
        ]


class SupplierService:
    """Service layer for supplier operations"""

    @staticmethod
    def get_suppliers(
        page: int = 1, per_page: int = 20, search: str = None, active_only: bool = True
    ) -> Tuple[List[Supplier], int]:
        query = Supplier.query

        if active_only:
            query = query.filter(Supplier.is_active.is_(True))

        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(
                    Supplier.name.ilike(search_term),
                    Supplier.contact_person.ilike(search_term),
                    Supplier.email.ilike(search_term),
                )
            )

        query = query.order_by(Supplier.name)
        # parts_count is rendered for every supplier; without this each row
        # triggers its own query for the association.
        query = query.options(selectinload(Supplier.parts))

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        SupplierService.attach_order_counts(pagination.items)
        return pagination.items, pagination.total

    @staticmethod
    def attach_order_counts(suppliers: List[Supplier]) -> None:
        """Populate ``purchase_order_count`` for a page of suppliers.

        ``Supplier.purchase_orders`` is a dynamic relationship, so calling
        ``.count()`` per row is one query each. This does the whole page in
        one grouped query.
        """
        if not suppliers:
            return

        from app.models import PurchaseOrder

        rows = (
            db.session.query(
                PurchaseOrder.supplier_id,
                func.count(PurchaseOrder.id).label("orders"),
            )
            .filter(PurchaseOrder.supplier_id.in_([s.id for s in suppliers]))
            .group_by(PurchaseOrder.supplier_id)
            .all()
        )

        counts = {row.supplier_id: int(row.orders or 0) for row in rows}
        for supplier in suppliers:
            supplier.purchase_order_count = counts.get(supplier.id, 0)

    @staticmethod
    def get_supplier(supplier_id: int) -> Optional[Supplier]:
        return db.session.get(Supplier, supplier_id)

    @staticmethod
    def _assert_unique_email(email: str, exclude_id: int = None) -> None:
        if not email:
            return
        query = Supplier.query.filter(Supplier.email == email)
        if exclude_id is not None:
            query = query.filter(Supplier.id != exclude_id)
        if query.first():
            raise ValueError(f'A supplier with the email "{email}" already exists')

    @staticmethod
    def create_supplier(data: dict) -> Supplier:
        SupplierService._assert_unique_email(data.get("email"))
        try:
            supplier = Supplier(**data)
            db.session.add(supplier)
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise
        return supplier

    @staticmethod
    def update_supplier(supplier_id: int, data: dict) -> Optional[Supplier]:
        supplier = db.session.get(Supplier, supplier_id)
        if not supplier:
            return None

        if data.get("email") and data["email"] != supplier.email:
            SupplierService._assert_unique_email(data["email"], exclude_id=supplier_id)

        try:
            for key, value in data.items():
                if hasattr(supplier, key) and key not in (
                    "id",
                    "created_at",
                    "updated_at",
                ):
                    setattr(supplier, key, value)
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise

        return supplier

    @staticmethod
    def delete_supplier(supplier_id: int) -> bool:
        """Deactivate a supplier with order history, hard-delete an unused one."""
        supplier = db.session.get(Supplier, supplier_id)
        if not supplier:
            return False

        try:
            if supplier.purchase_orders.count() > 0:
                supplier.is_active = False
            else:
                # Drop the association rows first; the m2m table has no
                # ORM-level cascade for a hard delete.
                db.session.execute(
                    supplier_part.delete().where(supplier_part.c.supplier_id == supplier_id)
                )
                db.session.delete(supplier)

            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise

        return True

    @staticmethod
    def link_part(supplier_id: int, part_id: int, data: dict = None) -> bool:
        """Link supplier to part"""
        supplier = db.session.get(Supplier, supplier_id)
        part = db.session.get(Part, part_id)
        if not supplier or not part:
            return False

        if part in supplier.parts:
            return True  # Already linked

        data = data or {}
        try:
            db.session.execute(
                supplier_part.insert().values(
                    supplier_id=supplier_id,
                    part_id=part_id,
                    supplier_sku=data.get("supplier_sku"),
                    cost_price=data.get("cost_price"),
                    lead_time_days=data.get("lead_time_days"),
                    is_preferred=data.get("is_preferred", False),
                )
            )
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise

        return True

    @staticmethod
    def unlink_part(supplier_id: int, part_id: int) -> bool:
        """Remove supplier-part link"""
        stmt = supplier_part.delete().where(
            supplier_part.c.supplier_id == supplier_id,
            supplier_part.c.part_id == part_id,
        )
        result = db.session.execute(stmt)
        db.session.commit()
        return result.rowcount > 0
