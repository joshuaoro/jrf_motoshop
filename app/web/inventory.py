"""
Web inventory blueprint
"""

import logging

from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from marshmallow import ValidationError

from app.api.utils import load_form
from app.models import Supplier
from app.services.inventory import InventoryService, SupplierService
from app.schemas import PartSchema, SupplierSchema

inventory_web_bp = Blueprint("inventory", __name__, template_folder="../../templates")
logger = logging.getLogger(__name__)


def _flash_validation(exc: ValidationError, action: str) -> None:
    """Turn marshmallow's nested error dict into readable flash messages."""
    for field, messages in exc.messages.items():
        if isinstance(messages, (list, tuple)):
            messages = "; ".join(str(m) for m in messages)
        flash(f"{action}: {field} - {messages}", "error")


@inventory_web_bp.route("/")
@login_required
def index():
    """Inventory page"""
    page = request.args.get("page", 1, type=int)
    per_page = 20
    search = request.args.get("search")
    part_type = request.args.get("type")
    brand = request.args.get("brand")
    low_stock = request.args.get("low_stock", "false").lower() == "true"

    parts, total = InventoryService.get_parts(
        page=page,
        per_page=per_page,
        search=search,
        part_type=part_type,
        brand=brand,
        low_stock_only=low_stock,
    )

    part_types = InventoryService.get_part_types()
    brands = InventoryService.get_brands()

    # Build parts data for template. ``stock_percent`` drives the stock bar:
    # 100% means "well stocked" (4x the reorder point), floored at 1% so a
    # near-empty part still shows a faint bar rather than nothing.
    parts_data = []
    for part in parts:
        data = part.to_dict()
        data["suppliers"] = [{"id": s.id, "name": s.name} for s in part.suppliers]
        health_cap = max(1, part.min_stock_level * 4)
        data["stock_percent"] = round(max(1, min(100, part.stock_quantity / health_cap * 100)))
        parts_data.append(data)

    return render_template(
        "inventory.html",
        parts=parts_data,
        parts_json=parts_data,
        pagination={
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": (total + per_page - 1) // per_page,
        },
        part_types=part_types,
        brands=brands,
        current_filters={
            "search": search,
            "type": part_type,
            "brand": brand,
            "low_stock": low_stock,
        },
    )


# ============================================================
# SUPPLIER ROUTES - MUST be before /<int:part_id> routes
# ============================================================
@inventory_web_bp.route("/suppliers")
@login_required
def suppliers():
    """Suppliers list"""
    page = request.args.get("page", 1, type=int)
    per_page = 20
    search = request.args.get("search")

    suppliers, total = SupplierService.get_suppliers(page, per_page, search)

    # Build suppliers data for template
    suppliers_data = []
    for supplier in suppliers:
        data = supplier.to_dict()
        # Both counts are pre-loaded in bulk by the service.
        data["total_purchase_orders"] = getattr(supplier, "purchase_order_count", 0)
        suppliers_data.append(data)

    return render_template(
        "suppliers.html",
        suppliers=suppliers_data,
        suppliers_json=suppliers_data,
        pagination={
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": (total + per_page - 1) // per_page,
        },
        search=search,
    )


@inventory_web_bp.route("/suppliers/create", methods=["GET", "POST"])
@login_required
def create_supplier():
    if not current_user.can_manage_suppliers():
        flash("Insufficient permissions", "error")
        return redirect(url_for("inventory.suppliers"))

    if request.method == "POST":
        try:
            data = load_form(SupplierSchema(), request.form)
            SupplierService.create_supplier(data)
        except ValidationError as exc:
            _flash_validation(exc, "Could not create supplier")
            return render_template("supplier_form.html", supplier=None), 400
        except ValueError as exc:
            flash(str(exc), "error")
            return render_template("supplier_form.html", supplier=None), 400

        flash("Supplier created successfully", "success")
        return redirect(url_for("inventory.suppliers"))

    return render_template("supplier_form.html", supplier=None)


@inventory_web_bp.route("/suppliers/<int:supplier_id>/edit", methods=["GET", "POST"])
@login_required
def edit_supplier(supplier_id):
    if not current_user.can_manage_suppliers():
        flash("Insufficient permissions", "error")
        return redirect(url_for("inventory.suppliers"))

    supplier = SupplierService.get_supplier(supplier_id)
    if not supplier:
        flash("Supplier not found", "error")
        return redirect(url_for("inventory.suppliers"))

    if request.method == "POST":
        try:
            # Persist the *validated* data. The previous version validated the
            # form and then saved request.form.to_dict() instead - so raw,
            # uncoerced strings went to the database and validation was moot.
            data = load_form(SupplierSchema(), request.form, partial=True)
            SupplierService.update_supplier(supplier_id, data)
        except ValidationError as exc:
            _flash_validation(exc, "Could not update supplier")
            return render_template("supplier_form.html", supplier=supplier), 400
        except ValueError as exc:
            flash(str(exc), "error")
            return render_template("supplier_form.html", supplier=supplier), 400

        flash("Supplier updated successfully", "success")
        return redirect(url_for("inventory.suppliers"))

    return render_template("supplier_form.html", supplier=supplier)


@inventory_web_bp.route("/suppliers/<int:supplier_id>/delete", methods=["POST"])
@login_required
def delete_supplier(supplier_id):
    if not current_user.can_manage_suppliers():
        flash("Insufficient permissions", "error")
        return redirect(url_for("inventory.suppliers"))

    success = SupplierService.delete_supplier(supplier_id)
    if success:
        flash("Supplier deleted successfully", "success")
    else:
        flash("Supplier not found", "error")

    return redirect(url_for("inventory.suppliers"))


# ============================================================
# PART ROUTES
# ============================================================
@inventory_web_bp.route("/create", methods=["GET", "POST"])
@login_required
def create():
    """Create new part"""
    if not current_user.can_manage_inventory():
        flash("Insufficient permissions", "error")
        return redirect(url_for("inventory.index"))

    suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()

    if request.method == "POST":
        try:
            # load_form (not schema.load) so a multi-select of supplier_ids
            # keeps every selected value instead of only the first.
            data = load_form(PartSchema(), request.form)
            InventoryService.create_part(data, current_user.id)
        except ValidationError as exc:
            _flash_validation(exc, "Could not create part")
            return render_template("inventory_form.html", part=None, suppliers=suppliers), 400
        except ValueError as exc:
            flash(str(exc), "error")
            return render_template("inventory_form.html", part=None, suppliers=suppliers), 400

        flash("Part created successfully", "success")
        return redirect(url_for("inventory.index"))

    return render_template("inventory_form.html", part=None, suppliers=suppliers)


@inventory_web_bp.route("/<int:part_id>/edit", methods=["GET", "POST"])
@login_required
def edit(part_id):
    """Edit part"""
    if not current_user.can_manage_inventory():
        flash("Insufficient permissions", "error")
        return redirect(url_for("inventory.index"))

    part = InventoryService.get_part(part_id)
    if not part:
        flash("Part not found", "error")
        return redirect(url_for("inventory.index"))

    suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()

    if request.method == "POST":
        try:
            data = load_form(PartSchema(), request.form, partial=True)
            updated = InventoryService.update_part(part_id, data, current_user.id)
        except ValidationError as exc:
            _flash_validation(exc, "Could not update part")
            return render_template("inventory_form.html", part=part, suppliers=suppliers), 400
        except ValueError as exc:
            flash(str(exc), "error")
            return render_template("inventory_form.html", part=part, suppliers=suppliers), 400

        flash(
            "Part updated successfully" if updated else "Part not found",
            "success" if updated else "error",
        )
        return redirect(url_for("inventory.index"))

    return render_template("inventory_form.html", part=part, suppliers=suppliers)


@inventory_web_bp.route("/<int:part_id>/delete", methods=["POST"])
@login_required
def delete(part_id):
    """Delete part"""
    if not current_user.can_manage_inventory():
        flash("Insufficient permissions", "error")
        return redirect(url_for("inventory.index"))

    success = InventoryService.delete_part(part_id)
    if success:
        flash("Part deleted successfully", "success")
    else:
        flash("Part not found", "error")

    return redirect(url_for("inventory.index"))
