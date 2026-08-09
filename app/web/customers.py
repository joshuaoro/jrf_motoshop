"""
Web customers blueprint
"""

import logging

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from marshmallow import ValidationError

from app.api.utils import load_form
from app.schemas import CustomerSchema
from app.services.sales import CustomerService

customers_web_bp = Blueprint("customers", __name__, template_folder="../../templates")
logger = logging.getLogger(__name__)

PER_PAGE = 20


def _flash_validation(exc: ValidationError, action: str) -> None:
    for field, messages in exc.messages.items():
        if isinstance(messages, (list, tuple)):
            messages = "; ".join(str(m) for m in messages)
        flash(f"{action}: {field} - {messages}", "error")


@customers_web_bp.route("/")
@login_required
def index():
    """Customers list page"""
    page = max(1, request.args.get("page", 1, type=int) or 1)
    search = request.args.get("search")

    customers, total = CustomerService.get_customers(page, PER_PAGE, search)

    customers_data = []
    for customer in customers:
        data = customer.to_dict()
        data["total_sales"] = customer.total_orders
        customers_data.append(data)

    return render_template(
        "customers.html",
        customers=customers_data,
        customers_json=customers_data,
        pagination={
            "page": page,
            "per_page": PER_PAGE,
            "total": total,
            "pages": (total + PER_PAGE - 1) // PER_PAGE,
        },
        search=search,
    )


@customers_web_bp.route("/create", methods=["POST"])
@login_required
def create():
    """Create new customer"""
    # Customer records are commercial data, not inventory - gate them on the
    # finance permission rather than can_manage_inventory().
    if not current_user.can_manage_finances():
        flash("Insufficient permissions", "error")
        return redirect(url_for("customers.index"))

    try:
        data = load_form(CustomerSchema(), request.form)
        customer = CustomerService.create_customer(data)
    except ValidationError as exc:
        _flash_validation(exc, "Could not create customer")
        return redirect(url_for("customers.index"))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("customers.index"))

    flash(f"Customer {customer.name} created successfully", "success")
    return redirect(url_for("customers.index"))


@customers_web_bp.route("/<int:customer_id>/edit", methods=["POST"])
@login_required
def edit(customer_id):
    """Update customer"""
    if not current_user.can_manage_finances():
        flash("Insufficient permissions", "error")
        return redirect(url_for("customers.index"))

    try:
        data = load_form(CustomerSchema(), request.form, partial=True)
        customer = CustomerService.update_customer(customer_id, data)
    except ValidationError as exc:
        _flash_validation(exc, "Could not update customer")
        return redirect(url_for("customers.index"))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("customers.index"))

    flash(
        "Customer updated successfully" if customer else "Customer not found",
        "success" if customer else "error",
    )
    return redirect(url_for("customers.index"))


@customers_web_bp.route("/<int:customer_id>/delete", methods=["POST"])
@login_required
def delete(customer_id):
    """Delete/deactivate customer"""
    if not current_user.can_manage_finances():
        flash("Insufficient permissions", "error")
        return redirect(url_for("customers.index"))

    if CustomerService.delete_customer(customer_id):
        flash("Customer deleted successfully", "success")
    else:
        flash("Customer not found", "error")

    return redirect(url_for("customers.index"))
