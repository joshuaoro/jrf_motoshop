"""
Customers API blueprint.

Mounted at ``/api/customers`` (canonical) and additionally at
``/api/sales/customers`` for the older nested paths. Customers are a top-level
resource - they exist independently of any sale - so the flat path is the one
to prefer in new code.
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
from app.schemas import customer_schema, customers_schema
from app.services.sales import CustomerService

customers_bp = Blueprint("customers_api", __name__)
logger = logging.getLogger(__name__)


@customers_bp.route("/", methods=["GET"])
@customers_bp.route("", methods=["GET"])
@login_required
def list_customers():
    """List customers"""
    page, per_page = pagination_args()
    customers, total = CustomerService.get_customers(
        page=page,
        per_page=per_page,
        search=request.args.get("search"),
        active_only=request.args.get("include_inactive", "false").lower() != "true",
    )

    return jsonify(
        {
            "customers": customers_schema.dump(customers),
            "pagination": pagination_meta(page, per_page, total),
        }
    )


@customers_bp.route("/", methods=["POST"])
@customers_bp.route("", methods=["POST"])
@login_required
def create_customer():
    """Create new customer"""
    data = load_json(customer_schema)
    try:
        customer = CustomerService.create_customer(data)
    except ValueError as exc:
        return error(str(exc), 400)

    return jsonify(customer_schema.dump(customer)), 201


@customers_bp.route("/<int:customer_id>", methods=["GET"])
@login_required
def get_customer(customer_id):
    """Get customer by ID"""
    customer = CustomerService.get_customer(customer_id)
    if not customer:
        return error("Customer not found", 404)
    return jsonify(customer_schema.dump(customer))


@customers_bp.route("/<int:customer_id>", methods=["PUT", "PATCH"])
@login_required
def update_customer(customer_id):
    """Update customer"""
    if not CustomerService.get_customer(customer_id):
        return error("Customer not found", 404)

    data = load_json(customer_schema, partial=True)
    try:
        customer = CustomerService.update_customer(customer_id, data)
    except ValueError as exc:
        return error(str(exc), 400)

    return jsonify(customer_schema.dump(customer))


@customers_bp.route("/<int:customer_id>", methods=["DELETE"])
@login_required
@permission_required("can_manage_finances")
def delete_customer(customer_id):
    """Delete a customer, or deactivate one that has sales history"""
    if not CustomerService.delete_customer(customer_id):
        return error("Customer not found", 404)
    return jsonify({"success": True, "message": "Customer deleted/deactivated successfully"})
