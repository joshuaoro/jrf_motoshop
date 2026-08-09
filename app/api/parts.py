"""
Parts API blueprint
"""

import logging

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from sqlalchemy import func

from app.core.extensions import db
from app.models import Sale, SaleDetail, StockEntry
from app.schemas import (
    StockAdjustmentSchema,
    part_schema,
    parts_schema,
    stock_entries_schema,
)
from app.api.utils import (
    error,
    load_json,
    pagination_args,
    pagination_meta,
    permission_required,
)
from app.services.inventory import InventoryService

parts_bp = Blueprint("parts", __name__)
logger = logging.getLogger(__name__)


@parts_bp.route("/", methods=["GET"])
@parts_bp.route("", methods=["GET"])
@login_required
def list_parts():
    """List parts with filters and pagination"""
    page, per_page = pagination_args()

    parts, total = InventoryService.get_parts(
        page=page,
        per_page=per_page,
        search=request.args.get("search"),
        part_type=request.args.get("type"),
        brand=request.args.get("brand"),
        low_stock_only=request.args.get("low_stock", "false").lower() == "true",
    )

    return jsonify(
        {
            "parts": parts_schema.dump(parts),
            "pagination": pagination_meta(page, per_page, total),
            "filters": {
                "types": InventoryService.get_part_types(),
                "brands": InventoryService.get_brands(),
            },
        }
    )


@parts_bp.route("/low-stock", methods=["GET"])
@login_required
def low_stock_parts():
    """Get low stock parts"""
    parts = InventoryService.get_low_stock_parts(request.args.get("threshold", type=int))
    return jsonify(parts_schema.dump(parts))


# Supplier endpoints live in app/api/suppliers.py. That blueprint is also
# mounted at /api/parts/suppliers, so the nested paths still resolve.


# ============================================================
# PART ENDPOINTS
# ============================================================
@parts_bp.route("/", methods=["POST"])
@parts_bp.route("", methods=["POST"])
@login_required
@permission_required("can_manage_inventory")
def create_part():
    """Create new part"""
    data = load_json(part_schema)
    try:
        part = InventoryService.create_part(data, current_user.id)
    except ValueError as exc:
        return error(str(exc), 400)

    logger.info("Part %s created by %s", part.sku, current_user.username)
    return jsonify(part_schema.dump(part)), 201


@parts_bp.route("/<int:part_id>", methods=["GET"])
@login_required
def get_part(part_id):
    """Get part by ID"""
    part = InventoryService.get_part(part_id)
    if not part:
        return error("Part not found", 404)
    return jsonify(part_schema.dump(part))


@parts_bp.route("/<int:part_id>", methods=["PUT"])
@login_required
@permission_required("can_manage_inventory")
def update_part(part_id):
    """Update part"""
    if not InventoryService.get_part(part_id):
        return error("Part not found", 404)

    data = load_json(part_schema, partial=True)
    try:
        part = InventoryService.update_part(part_id, data, current_user.id)
    except ValueError as exc:
        return error(str(exc), 400)

    if not part:
        return error("Part not found", 404)
    return jsonify(part_schema.dump(part))


@parts_bp.route("/<int:part_id>", methods=["DELETE"])
@login_required
@permission_required("can_manage_inventory")
def delete_part(part_id):
    """Delete/deactivate part"""
    if not InventoryService.delete_part(part_id):
        return error("Part not found", 404)
    return jsonify({"message": "Part deleted/deactivated successfully"})


@parts_bp.route("/<int:part_id>/stock", methods=["POST"])
@login_required
@permission_required("can_manage_inventory")
def adjust_stock(part_id):
    """Adjust stock quantity"""
    data = load_json(StockAdjustmentSchema())

    try:
        part = InventoryService.adjust_stock(
            part_id=part_id,
            quantity_change=data["quantity_change"],
            movement_type=data["movement_type"],
            reference_type=data.get("reference_type"),
            reference_id=data.get("reference_id"),
            notes=data.get("notes"),
            user_id=current_user.id,
        )
    except ValueError as exc:
        return error(str(exc), 400)

    if not part:
        return error("Part not found", 404)
    return jsonify(part_schema.dump(part))


@parts_bp.route("/<int:part_id>/sales-metrics", methods=["GET"])
@login_required
def sales_metrics(part_id):
    """Lifetime sales performance for one part.

    Backs the metrics panel in the inventory detail modal, which previously
    called this path and always got a 404.
    """
    if not InventoryService.get_part(part_id):
        return error("Part not found", 404)

    row = (
        db.session.query(
            func.coalesce(func.sum(SaleDetail.quantity), 0).label("total_sold"),
            func.coalesce(func.sum(SaleDetail.line_total), 0).label("total_revenue"),
            func.coalesce(func.sum(SaleDetail.unit_cost * SaleDetail.quantity), 0).label(
                "total_cost"
            ),
            func.count(SaleDetail.sale_id).label("sale_count"),
        )
        .join(Sale, Sale.id == SaleDetail.sale_id)
        .filter(
            SaleDetail.part_id == part_id,
            Sale.payment_status != "refunded",
        )
        .one()
    )

    total_sold = int(row.total_sold or 0)
    total_revenue = float(row.total_revenue or 0)
    total_cost = float(row.total_cost or 0)

    return jsonify(
        {
            "part_id": part_id,
            "total_sold": total_sold,
            "sale_count": int(row.sale_count or 0),
            "total_revenue": total_revenue,
            "total_cost": total_cost,
            "gross_profit": total_revenue - total_cost,
            "avg_price": round(total_revenue / total_sold, 2) if total_sold else 0.0,
        }
    )


@parts_bp.route("/<int:part_id>/stock-history", methods=["GET"])
@login_required
def stock_history(part_id):
    """Get stock movement history for a part"""
    if not InventoryService.get_part(part_id):
        return error("Part not found", 404)

    page, per_page = pagination_args(default_per_page=50)
    entries = (
        StockEntry.query.filter_by(part_id=part_id)
        .order_by(StockEntry.entry_date.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    return jsonify(
        {
            "entries": stock_entries_schema.dump(entries.items),
            "pagination": pagination_meta(page, per_page, entries.total),
        }
    )
