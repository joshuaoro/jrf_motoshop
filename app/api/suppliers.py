"""
Suppliers API blueprint.

Mounted at ``/api/suppliers`` (canonical) and additionally at
``/api/parts/suppliers`` for the older nested paths.
"""

import logging

from flask import Blueprint, jsonify, request
from flask_login import login_required

from app.api.utils import (
    error,
    load_json,
    pagination_args,
    pagination_meta,
    permission_required,
)
from app.schemas import SupplierPartLinkSchema, supplier_schema, suppliers_schema
from app.services.inventory import SupplierService

suppliers_bp = Blueprint("suppliers_api", __name__)
logger = logging.getLogger(__name__)


@suppliers_bp.route("/", methods=["GET"])
@suppliers_bp.route("", methods=["GET"])
@login_required
def list_suppliers():
    """List suppliers"""
    page, per_page = pagination_args()
    suppliers, total = SupplierService.get_suppliers(
        page=page,
        per_page=per_page,
        search=request.args.get("search"),
        active_only=request.args.get("include_inactive", "false").lower() != "true",
    )

    return jsonify(
        {
            "suppliers": suppliers_schema.dump(suppliers),
            "pagination": pagination_meta(page, per_page, total),
        }
    )


@suppliers_bp.route("/", methods=["POST"])
@suppliers_bp.route("", methods=["POST"])
@login_required
@permission_required("can_manage_suppliers")
def create_supplier():
    """Create new supplier"""
    data = load_json(supplier_schema)
    try:
        supplier = SupplierService.create_supplier(data)
    except ValueError as exc:
        return error(str(exc), 400)

    return jsonify(supplier_schema.dump(supplier)), 201


@suppliers_bp.route("/<int:supplier_id>", methods=["GET"])
@login_required
def get_supplier(supplier_id):
    """Get supplier by ID"""
    supplier = SupplierService.get_supplier(supplier_id)
    if not supplier:
        return error("Supplier not found", 404)
    return jsonify(supplier_schema.dump(supplier))


@suppliers_bp.route("/<int:supplier_id>", methods=["PUT", "PATCH"])
@login_required
@permission_required("can_manage_suppliers")
def update_supplier(supplier_id):
    """Update supplier"""
    if not SupplierService.get_supplier(supplier_id):
        return error("Supplier not found", 404)

    data = load_json(supplier_schema, partial=True)
    try:
        supplier = SupplierService.update_supplier(supplier_id, data)
    except ValueError as exc:
        return error(str(exc), 400)

    return jsonify(supplier_schema.dump(supplier))


@suppliers_bp.route("/<int:supplier_id>", methods=["DELETE"])
@login_required
@permission_required("can_manage_suppliers")
def delete_supplier(supplier_id):
    """Delete a supplier, or deactivate one that has purchase orders"""
    if not SupplierService.delete_supplier(supplier_id):
        return error("Supplier not found", 404)
    return jsonify({"success": True, "message": "Supplier deleted/deactivated successfully"})


@suppliers_bp.route("/<int:supplier_id>/parts", methods=["GET"])
@login_required
def list_supplier_parts(supplier_id):
    """Parts supplied by this supplier"""
    supplier = SupplierService.get_supplier(supplier_id)
    if not supplier:
        return error("Supplier not found", 404)

    return jsonify(
        [
            {"id": p.id, "name": p.name, "sku": p.sku, "price": float(p.price or 0)}
            for p in supplier.parts
        ]
    )


@suppliers_bp.route("/<int:supplier_id>/parts", methods=["POST"])
@login_required
@permission_required("can_manage_inventory")
def link_supplier_part(supplier_id):
    """Link supplier to part"""
    payload = request.get_json(silent=True) or {}
    part_id = payload.get("part_id")
    if not part_id:
        return error("part_id required", 400)

    link_data = load_json(SupplierPartLinkSchema(), partial=True)
    if not SupplierService.link_part(supplier_id, part_id, link_data):
        return error("Supplier or part not found", 404)

    return jsonify({"success": True, "message": "Supplier linked to part successfully"})


@suppliers_bp.route("/<int:supplier_id>/parts/<int:part_id>", methods=["DELETE"])
@login_required
@permission_required("can_manage_inventory")
def unlink_supplier_part(supplier_id, part_id):
    """Unlink supplier from part"""
    if not SupplierService.unlink_part(supplier_id, part_id):
        return error("Link not found", 404)
    return jsonify({"success": True, "message": "Supplier unlinked from part"})
