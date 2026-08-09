"""
Web suppliers blueprint
"""

import logging

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from marshmallow import ValidationError

from app.api.utils import load_form
from app.schemas import SupplierSchema
from app.services.inventory import SupplierService

suppliers_web_bp = Blueprint("suppliers", __name__, template_folder="../../templates")
logger = logging.getLogger(__name__)

PER_PAGE = 20


def _flash_validation(exc: ValidationError, action: str) -> None:
    for field, messages in exc.messages.items():
        if isinstance(messages, (list, tuple)):
            messages = "; ".join(str(m) for m in messages)
        flash(f"{action}: {field} - {messages}", "error")


@suppliers_web_bp.route("/")
@login_required
def index():
    """Suppliers list page"""
    page = max(1, request.args.get("page", 1, type=int) or 1)
    search = request.args.get("search")

    suppliers, total = SupplierService.get_suppliers(page, PER_PAGE, search)

    suppliers_data = []
    for supplier in suppliers:
        data = supplier.to_dict()
        # Pre-loaded in bulk by the service; no per-row query here.
        data["total_purchase_orders"] = getattr(supplier, "purchase_order_count", 0)
        suppliers_data.append(data)

    return render_template(
        "suppliers.html",
        suppliers=suppliers_data,
        suppliers_json=suppliers_data,
        pagination={
            "page": page,
            "per_page": PER_PAGE,
            "total": total,
            "pages": (total + PER_PAGE - 1) // PER_PAGE,
        },
        search=search,
    )


@suppliers_web_bp.route("/create", methods=["POST"])
@login_required
def create():
    """Create new supplier"""
    if not current_user.can_manage_suppliers():
        flash("Insufficient permissions", "error")
        return redirect(url_for("suppliers.index"))

    try:
        data = load_form(SupplierSchema(), request.form)
        supplier = SupplierService.create_supplier(data)
    except ValidationError as exc:
        _flash_validation(exc, "Could not create supplier")
        return redirect(url_for("suppliers.index"))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("suppliers.index"))

    flash(f"Supplier {supplier.name} created successfully", "success")
    return redirect(url_for("suppliers.index"))


@suppliers_web_bp.route("/<int:supplier_id>/edit", methods=["POST"])
@login_required
def edit(supplier_id):
    """Update supplier"""
    if not current_user.can_manage_suppliers():
        flash("Insufficient permissions", "error")
        return redirect(url_for("suppliers.index"))

    try:
        data = load_form(SupplierSchema(), request.form, partial=True)
        supplier = SupplierService.update_supplier(supplier_id, data)
    except ValidationError as exc:
        _flash_validation(exc, "Could not update supplier")
        return redirect(url_for("suppliers.index"))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("suppliers.index"))

    flash(
        "Supplier updated successfully" if supplier else "Supplier not found",
        "success" if supplier else "error",
    )
    return redirect(url_for("suppliers.index"))


@suppliers_web_bp.route("/<int:supplier_id>/delete", methods=["POST"])
@login_required
def delete(supplier_id):
    """Delete supplier"""
    if not current_user.can_manage_suppliers():
        flash("Insufficient permissions", "error")
        return redirect(url_for("suppliers.index"))

    if SupplierService.delete_supplier(supplier_id):
        flash("Supplier deleted successfully", "success")
    else:
        flash("Supplier not found", "error")

    return redirect(url_for("suppliers.index"))
