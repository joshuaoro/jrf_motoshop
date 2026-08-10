"""
Sales API blueprint
"""

import logging

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from app.api.utils import (
    error,
    load_json,
    pagination_args,
    pagination_meta,
    parse_date_arg,
    permission_required,
)
from app.models import Payment
from app.schemas import (
    PaymentSchema,
    VoidSaleSchema,
    payments_schema,
    sale_create_schema,
    sale_schema,
    sales_schema,
)
from app.services.sales import SalesService

sales_bp = Blueprint("sales", __name__)
logger = logging.getLogger(__name__)


@sales_bp.route("/", methods=["GET"])
@sales_bp.route("", methods=["GET"])
@login_required
def list_sales():
    """List sales with filters"""
    page, per_page = pagination_args()

    sales, total = SalesService.get_sales(
        page=page,
        per_page=per_page,
        start_date=parse_date_arg("start_date"),
        end_date=parse_date_arg("end_date", end_of_day=True),
        staff_id=request.args.get("staff_id", type=int),
        customer_id=request.args.get("customer_id", type=int),
        payment_status=request.args.get("payment_status"),
    )

    return jsonify(
        {
            "sales": sales_schema.dump(sales),
            "pagination": pagination_meta(page, per_page, total),
        }
    )


# Customer endpoints live in app/api/customers.py. That blueprint is also
# mounted at /api/sales/customers, so the nested paths still resolve.


# ============================================================
# SUMMARY & STATS ENDPOINTS - MUST be before /<int:sale_id>
# ============================================================
@sales_bp.route("/summary", methods=["GET"])
@login_required
def sales_summary():
    """Get sales summary for date range"""
    summary = SalesService.get_sales_summary(
        parse_date_arg("start_date"),
        parse_date_arg("end_date", end_of_day=True),
    )
    return jsonify(summary)


@sales_bp.route("/top-parts", methods=["GET"])
@login_required
def top_selling_parts():
    """Get top selling parts"""
    limit = request.args.get("limit", 10, type=int) or 10
    parts = SalesService.get_top_selling_parts(
        limit,
        parse_date_arg("start_date"),
        parse_date_arg("end_date", end_of_day=True),
    )
    return jsonify(parts)


# ============================================================
# SALE ENDPOINTS
# ============================================================
@sales_bp.route("/", methods=["POST"])
@sales_bp.route("", methods=["POST"])
@login_required
def create_sale():
    """Create new sale"""
    data = load_json(sale_create_schema)

    try:
        sale = SalesService.create_sale(data, current_user.id)
    except ValueError as exc:
        return error(str(exc), 400)

    logger.info(
        "Sale %s created by %s (total %s)",
        sale.receipt_number,
        current_user.username,
        sale.total_amount,
    )
    return jsonify(sale_schema.dump(sale)), 201


@sales_bp.route("/<int:sale_id>", methods=["GET"])
@login_required
def get_sale(sale_id):
    """Get sale by ID with details"""
    sale = SalesService.get_sale(sale_id)
    if not sale:
        return error("Sale not found", 404)
    return jsonify(sale_schema.dump(sale))


@sales_bp.route("/<int:sale_id>/payments", methods=["GET"])
@login_required
def get_sale_payments(sale_id):
    """Get payments for a sale"""
    sale = SalesService.get_sale(sale_id)
    if not sale:
        return error("Sale not found", 404)

    payments = Payment.query.filter_by(sale_id=sale_id).order_by(Payment.payment_date.desc()).all()

    return jsonify(
        {
            "payments": payments_schema.dump(payments),
            "total_amount": float(sale.total_amount),
            "amount_paid": float(SalesService.get_amount_paid(sale)),
            "balance": float(sale.total_amount - SalesService.get_amount_paid(sale)),
        }
    )


@sales_bp.route("/<int:sale_id>/payments", methods=["POST"])
@login_required
def add_payment(sale_id):
    """Add payment to sale"""
    data = load_json(PaymentSchema())

    try:
        payment = SalesService.process_payment(
            sale_id=sale_id,
            amount=data["amount"],
            payment_method=data["payment_method"],
            reference_number=data.get("reference_number"),
            notes=data.get("notes"),
            user_id=current_user.id,
        )
    except ValueError as exc:
        message = str(exc)
        return error(message, 404 if message == "Sale not found" else 400)

    return jsonify(PaymentSchema().dump(payment)), 201


@sales_bp.route("/<int:sale_id>/void", methods=["POST"])
@login_required
@permission_required("can_manage_inventory")
def void_sale(sale_id):
    """Void a sale (restore stock)"""
    data = load_json(VoidSaleSchema())

    if not SalesService.void_sale(sale_id, current_user.id, data["reason"]):
        return error("Sale not found or already voided", 404)

    logger.info("Sale %s voided by %s", sale_id, current_user.username)
    return jsonify({"message": "Sale voided successfully"})
