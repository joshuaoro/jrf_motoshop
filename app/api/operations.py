"""
Operations API - expenses, purchase orders and maintenance logs.

Three blueprints in one module because they share the same shape and the same
narrow audience (managers and administrators). Mounted at /api/expenses,
/api/purchase-orders and /api/maintenance.
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
from app.schemas import (
    ExpenseSchema,
    ReceiveItemsSchema,
    expenses_schema,
    maintenance_log_schema,
    maintenance_logs_schema,
    purchase_order_schema,
    purchase_orders_schema,
)
from app.services.operations import (
    ExpenseService,
    MaintenanceService,
    PurchaseOrderService,
)

logger = logging.getLogger(__name__)

expenses_bp = Blueprint("expenses", __name__)
purchase_orders_bp = Blueprint("purchase_orders", __name__)
maintenance_bp = Blueprint("maintenance", __name__)

expense_schema = ExpenseSchema()


# ============================================================
# EXPENSES
# ============================================================
@expenses_bp.route("/", methods=["GET"])
@expenses_bp.route("", methods=["GET"])
@login_required
@permission_required("can_manage_finances")
def list_expenses():
    """List expenses with optional category and date filters."""
    page, per_page = pagination_args()
    expenses, total = ExpenseService.get_expenses(
        page=page,
        per_page=per_page,
        category=request.args.get("category"),
        start_date=parse_date_arg("start_date"),
        end_date=parse_date_arg("end_date", end_of_day=True),
        search=request.args.get("search"),
    )

    return jsonify(
        {
            "expenses": expenses_schema.dump(expenses),
            "pagination": pagination_meta(page, per_page, total),
        }
    )


@expenses_bp.route("/", methods=["POST"])
@expenses_bp.route("", methods=["POST"])
@login_required
@permission_required("can_manage_finances")
def create_expense():
    """Record a business expense."""
    data = load_json(expense_schema)
    expense = ExpenseService.create_expense(data, current_user.id)

    logger.info(
        "Expense %s recorded by %s (%s)",
        expense.id,
        current_user.username,
        expense.amount,
    )
    return jsonify(expense_schema.dump(expense)), 201


@expenses_bp.route("/<int:expense_id>", methods=["GET"])
@login_required
@permission_required("can_manage_finances")
def get_expense(expense_id):
    expense = ExpenseService.get_expense(expense_id)
    if not expense:
        return error("Expense not found", 404)
    return jsonify(expense_schema.dump(expense))


@expenses_bp.route("/<int:expense_id>", methods=["PUT", "PATCH"])
@login_required
@permission_required("can_manage_finances")
def update_expense(expense_id):
    if not ExpenseService.get_expense(expense_id):
        return error("Expense not found", 404)

    data = load_json(expense_schema, partial=True)
    expense = ExpenseService.update_expense(expense_id, data)
    return jsonify(expense_schema.dump(expense))


@expenses_bp.route("/<int:expense_id>", methods=["DELETE"])
@login_required
@permission_required("can_manage_finances")
def delete_expense(expense_id):
    if not ExpenseService.delete_expense(expense_id):
        return error("Expense not found", 404)
    return jsonify({"success": True, "message": "Expense deleted"})


# ============================================================
# PURCHASE ORDERS
# ============================================================
@purchase_orders_bp.route("/", methods=["GET"])
@purchase_orders_bp.route("", methods=["GET"])
@login_required
@permission_required("can_manage_inventory")
def list_orders():
    page, per_page = pagination_args()
    orders, total = PurchaseOrderService.get_orders(
        page=page,
        per_page=per_page,
        supplier_id=request.args.get("supplier_id", type=int),
        status=request.args.get("status"),
    )

    return jsonify(
        {
            "purchase_orders": purchase_orders_schema.dump(orders),
            "pagination": pagination_meta(page, per_page, total),
        }
    )


@purchase_orders_bp.route("/", methods=["POST"])
@purchase_orders_bp.route("", methods=["POST"])
@login_required
@permission_required("can_manage_inventory")
def create_order():
    """Raise a purchase order. Totals are computed from the line items."""
    data = load_json(purchase_order_schema)

    try:
        order = PurchaseOrderService.create_order(data, current_user.id)
    except ValueError as exc:
        return error(str(exc), 400)

    logger.info("Purchase order %s raised by %s", order.order_number, current_user.username)
    return jsonify(purchase_order_schema.dump(order)), 201


@purchase_orders_bp.route("/<int:order_id>", methods=["GET"])
@login_required
@permission_required("can_manage_inventory")
def get_order(order_id):
    order = PurchaseOrderService.get_order(order_id)
    if not order:
        return error("Purchase order not found", 404)
    return jsonify(purchase_order_schema.dump(order))


@purchase_orders_bp.route("/<int:order_id>/status", methods=["POST"])
@login_required
@permission_required("can_manage_inventory")
def set_order_status(order_id):
    """Advance a purchase order to a new status."""
    payload = request.get_json(silent=True) or {}
    status = payload.get("status")
    if not status:
        return error("A 'status' is required", 400)

    try:
        order = PurchaseOrderService.set_status(order_id, status)
    except ValueError as exc:
        return error(str(exc), 400)

    if not order:
        return error("Purchase order not found", 404)
    return jsonify(purchase_order_schema.dump(order))


@purchase_orders_bp.route("/<int:order_id>/receive", methods=["POST"])
@login_required
@permission_required("can_manage_inventory")
def receive_order(order_id):
    """Book goods in against a purchase order and increase stock."""
    data = load_json(ReceiveItemsSchema())

    try:
        order = PurchaseOrderService.receive_items(order_id, data["items"], current_user.id)
    except ValueError as exc:
        message = str(exc)
        return error(message, 404 if message == "Purchase order not found" else 400)

    logger.info(
        "Goods received against %s by %s (status now %s)",
        order.order_number,
        current_user.username,
        order.status,
    )
    return jsonify(purchase_order_schema.dump(order))


@purchase_orders_bp.route("/<int:order_id>", methods=["DELETE"])
@login_required
@permission_required("can_manage_inventory")
def delete_order(order_id):
    try:
        deleted = PurchaseOrderService.delete_order(order_id)
    except ValueError as exc:
        return error(str(exc), 400)

    if not deleted:
        return error("Purchase order not found", 404)
    return jsonify({"success": True, "message": "Purchase order deleted"})


# ============================================================
# MAINTENANCE
# ============================================================
@maintenance_bp.route("/", methods=["GET"])
@maintenance_bp.route("", methods=["GET"])
@login_required
@permission_required("can_manage_inventory")
def list_maintenance():
    page, per_page = pagination_args()
    logs, total = MaintenanceService.get_logs(
        page=page,
        per_page=per_page,
        maintenance_type=request.args.get("type"),
        overdue_only=request.args.get("overdue", "false").lower() == "true",
    )

    return jsonify(
        {
            "maintenance_logs": maintenance_logs_schema.dump(logs),
            "pagination": pagination_meta(page, per_page, total),
        }
    )


@maintenance_bp.route("/", methods=["POST"])
@maintenance_bp.route("", methods=["POST"])
@login_required
@permission_required("can_manage_inventory")
def create_maintenance():
    data = load_json(maintenance_log_schema)

    try:
        log = MaintenanceService.create_log(data, current_user.id)
    except ValueError as exc:
        return error(str(exc), 400)

    return jsonify(maintenance_log_schema.dump(log)), 201


@maintenance_bp.route("/<int:log_id>", methods=["GET"])
@login_required
@permission_required("can_manage_inventory")
def get_maintenance(log_id):
    log = MaintenanceService.get_log(log_id)
    if not log:
        return error("Maintenance log not found", 404)
    return jsonify(maintenance_log_schema.dump(log))


@maintenance_bp.route("/<int:log_id>", methods=["PUT", "PATCH"])
@login_required
@permission_required("can_manage_inventory")
def update_maintenance(log_id):
    if not MaintenanceService.get_log(log_id):
        return error("Maintenance log not found", 404)

    data = load_json(maintenance_log_schema, partial=True)
    log = MaintenanceService.update_log(log_id, data)
    return jsonify(maintenance_log_schema.dump(log))


@maintenance_bp.route("/<int:log_id>", methods=["DELETE"])
@login_required
@permission_required("can_manage_inventory")
def delete_maintenance(log_id):
    if not MaintenanceService.delete_log(log_id):
        return error("Maintenance log not found", 404)
    return jsonify({"success": True, "message": "Maintenance log deleted"})
