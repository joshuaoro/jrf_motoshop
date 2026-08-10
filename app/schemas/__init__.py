"""
Marshmallow schemas for request validation and response serialization.

Two conventions are enforced here, and the service layer depends on both:

1. ``load()`` always returns a plain ``dict`` (``load_instance`` is never
   enabled). Services build/patch models themselves - e.g. ``Part(**data)`` and
   ``for key, value in data.items()`` - so a model instance from ``load()``
   would break them.
2. Server-computed and identity fields are ``dump_only``. A client can never
   set ``id``, ``receipt_number``, ``total_amount`` or timestamps by putting
   them in a payload.

Schemas accept both JSON bodies and HTML form submissions. Because form posts
send everything as strings and send ``''`` for empty inputs, ``_BaseSchema``
normalises blank strings to ``None`` before field validation runs.
"""

from decimal import Decimal

from marshmallow import (
    EXCLUDE,
    Schema,
    ValidationError,
    fields,
    pre_load,
    validate,
    validates_schema,
)
from marshmallow.utils import missing as missing_


# ============================================================
# BASE
# ============================================================
class _BaseSchema(Schema):
    """Shared behaviour for every schema in the app."""

    class Meta:
        # Ignore unexpected keys instead of erroring. HTML forms carry extras
        # (csrf_token, submit buttons) that are not part of the model.
        unknown = EXCLUDE
        ordered = True

    @pre_load
    def _normalise_input(self, data, **kwargs):
        """Trim strings and decide what an empty HTML input means.

        An empty text box posts ``''``. Raw, that fails validation on every
        Integer/Decimal/Date field even when the field is optional. So ``''``
        becomes ``None``, and then:

        * for a nullable field, ``None`` is kept - the user is clearing it;
        * for a non-nullable field that has a ``load_default``, the key is
          dropped so the default applies (a blank ``credit_limit`` box means
          "leave it at 0", not "set it to null");
        * otherwise ``None`` is kept so a genuinely required field still
          reports itself as missing.
        """
        if not isinstance(data, dict):
            # Werkzeug MultiDict and friends - flatten to a plain dict.
            try:
                data = dict(data)
            except (TypeError, ValueError):
                return data

        by_key = {(field.data_key or name): field for name, field in self.fields.items()}

        cleaned = {}
        for key, value in data.items():
            if isinstance(value, str):
                value = value.strip()
                if value == "":
                    value = None

            if value is None:
                field = by_key.get(key)
                if (
                    field is not None
                    and not field.allow_none
                    and field.load_default is not missing_
                ):
                    continue  # let the declared default win

            cleaned[key] = value
        return cleaned


class _Money(fields.Decimal):
    """Currency field.

    Loads as ``Decimal`` so arithmetic in the service layer stays exact, and
    dumps as ``float`` to match the ``to_dict()`` output used by the rest of
    the API and by the front-end JavaScript.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("places", 2)
        kwargs.setdefault("rounding", None)
        super().__init__(**kwargs)

    def _serialize(self, value, attr, obj, **kwargs):
        if value is None:
            return None
        return float(value)


# ============================================================
# USER / STAFF
# ============================================================
from app.models.user import VALID_ROLES


class UserSchema(_BaseSchema):
    id = fields.Integer(dump_only=True)
    name = fields.String(required=True, validate=validate.Length(min=1, max=100))
    role = fields.String(load_default="staff", validate=validate.OneOf(VALID_ROLES))
    contact_no = fields.String(allow_none=True, validate=validate.Length(max=20))
    email = fields.Email(required=True, validate=validate.Length(max=100))
    username = fields.String(required=True, validate=validate.Length(min=3, max=80))
    password = fields.String(load_only=True, validate=validate.Length(min=8, max=200))
    is_active = fields.Boolean(load_default=True)

    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
    last_login = fields.DateTime(dump_only=True)


# ============================================================
# INVENTORY
# ============================================================
class PartSchema(_BaseSchema):
    id = fields.Integer(dump_only=True)
    name = fields.String(required=True, validate=validate.Length(min=1, max=100))
    description = fields.String(allow_none=True)
    part_type = fields.String(allow_none=True, validate=validate.Length(max=50))
    brand = fields.String(allow_none=True, validate=validate.Length(max=50))
    price = _Money(required=True, validate=validate.Range(min=Decimal("0")))
    cost_price = _Money(load_default=Decimal("0"), validate=validate.Range(min=Decimal("0")))
    stock_quantity = fields.Integer(load_default=0, validate=validate.Range(min=0))
    min_stock_level = fields.Integer(load_default=5, validate=validate.Range(min=0))
    sku = fields.String(allow_none=True, validate=validate.Length(max=50))
    barcode = fields.String(allow_none=True, validate=validate.Length(max=100))
    location = fields.String(allow_none=True, validate=validate.Length(max=50))
    is_active = fields.Boolean(load_default=True)

    supplier_ids = fields.List(fields.Integer(), load_only=True, required=False)

    # Computed, read-only
    stock_status = fields.String(dump_only=True)
    stock_value = fields.Float(dump_only=True)
    stock_cost = fields.Float(dump_only=True)
    margin_percent = fields.Float(dump_only=True)
    is_low_stock = fields.Boolean(dump_only=True)
    suppliers = fields.Method("_dump_suppliers", dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)

    def _dump_suppliers(self, obj):
        suppliers = getattr(obj, "suppliers", None) or []
        return [{"id": s.id, "name": s.name} for s in suppliers]


class SupplierSchema(_BaseSchema):
    id = fields.Integer(dump_only=True)
    name = fields.String(required=True, validate=validate.Length(min=1, max=100))
    contact_no = fields.String(allow_none=True, validate=validate.Length(max=20))
    email = fields.Email(allow_none=True, validate=validate.Length(max=100))
    address = fields.String(allow_none=True)
    contact_person = fields.String(allow_none=True, validate=validate.Length(max=100))
    payment_terms = fields.String(allow_none=True, validate=validate.Length(max=50))
    is_active = fields.Boolean(load_default=True)

    parts_count = fields.Method("_dump_parts_count", dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)

    def _dump_parts_count(self, obj):
        return len(getattr(obj, "parts", None) or [])


class SupplierPartLinkSchema(_BaseSchema):
    """Extra attributes stored on the supplier<->part association."""

    supplier_sku = fields.String(allow_none=True, validate=validate.Length(max=50))
    cost_price = _Money(allow_none=True, validate=validate.Range(min=Decimal("0")))
    lead_time_days = fields.Integer(allow_none=True, validate=validate.Range(min=0))
    is_preferred = fields.Boolean(load_default=False)


class StockAdjustmentSchema(_BaseSchema):
    """Payload for adjusting a part's stock level."""

    quantity_change = fields.Integer(required=True)
    movement_type = fields.String(
        load_default="adjustment",
        validate=validate.OneOf(("sale", "purchase", "adjustment", "return", "transfer")),
    )
    reference_type = fields.String(allow_none=True, validate=validate.Length(max=20))
    reference_id = fields.Integer(allow_none=True)
    notes = fields.String(allow_none=True)

    @validates_schema
    def _reject_zero(self, data, **kwargs):
        if data.get("quantity_change") == 0:
            raise ValidationError({"quantity_change": ["Quantity change cannot be zero."]})


class StockEntrySchema(_BaseSchema):
    id = fields.Integer(dump_only=True)
    entry_date = fields.DateTime(dump_only=True)
    quantity = fields.Integer(dump_only=True)
    movement_type = fields.String(dump_only=True)
    reference_type = fields.String(dump_only=True)
    reference_id = fields.Integer(dump_only=True)
    notes = fields.String(dump_only=True)
    part_id = fields.Integer(dump_only=True)
    created_by = fields.Integer(dump_only=True)


# ============================================================
# CUSTOMERS & SALES
# ============================================================
class CustomerSchema(_BaseSchema):
    id = fields.Integer(dump_only=True)
    name = fields.String(required=True, validate=validate.Length(min=1, max=100))
    email = fields.Email(allow_none=True, validate=validate.Length(max=100))
    phone = fields.String(allow_none=True, validate=validate.Length(max=20))
    address = fields.String(allow_none=True)
    city = fields.String(allow_none=True, validate=validate.Length(max=50))
    postal_code = fields.String(allow_none=True, validate=validate.Length(max=20))
    tax_id = fields.String(allow_none=True, validate=validate.Length(max=50))
    credit_limit = _Money(load_default=Decimal("0"), validate=validate.Range(min=Decimal("0")))
    balance = _Money(dump_only=True)
    is_active = fields.Boolean(load_default=True)
    notes = fields.String(allow_none=True)

    total_spent = fields.Float(dump_only=True)
    total_orders = fields.Integer(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)


PAYMENT_METHODS = ("cash", "card", "gcash", "bank_transfer", "cheque")
PAYMENT_STATUSES = ("paid", "partial", "pending", "refunded")


class SaleLineSchema(_BaseSchema):
    """One line item on an incoming sale."""

    part_id = fields.Integer(required=True)
    quantity = fields.Integer(required=True, validate=validate.Range(min=1))
    # Optional: falls back to the part's current catalogue price server-side.
    unit_price = _Money(allow_none=True, validate=validate.Range(min=Decimal("0")))
    discount_percent = _Money(
        load_default=Decimal("0"),
        validate=validate.Range(min=Decimal("0"), max=Decimal("100")),
    )
    tax_percent = _Money(
        load_default=Decimal("0"),
        validate=validate.Range(min=Decimal("0"), max=Decimal("100")),
    )


class SaleDetailSchema(_BaseSchema):
    """Serialised sale line (read-only)."""

    sale_id = fields.Integer(dump_only=True)
    part_id = fields.Integer(dump_only=True)
    part_name = fields.Method("_dump_part_name", dump_only=True)
    part_sku = fields.Method("_dump_part_sku", dump_only=True)
    quantity = fields.Integer(dump_only=True)
    unit_price = _Money(dump_only=True)
    unit_cost = _Money(dump_only=True)
    discount_percent = _Money(dump_only=True)
    discount_amount = _Money(dump_only=True)
    tax_percent = _Money(dump_only=True)
    tax_amount = _Money(dump_only=True)
    line_total = _Money(dump_only=True)
    line_cost = fields.Float(dump_only=True)
    line_profit = fields.Float(dump_only=True)

    def _dump_part_name(self, obj):
        part = getattr(obj, "part", None)
        return part.name if part else None

    def _dump_part_sku(self, obj):
        part = getattr(obj, "part", None)
        return part.sku if part else None


class SaleSchema(_BaseSchema):
    """Sale create payload + sale serialisation.

    ``total_amount``, ``tax_amount``, ``discount_amount`` and
    ``receipt_number`` are deliberately dump-only: they are derived from the
    line items by ``SalesService.create_sale`` so a client cannot dictate the
    price it pays.
    """

    id = fields.Integer(dump_only=True)
    sale_date = fields.DateTime(allow_none=True)
    payment_method = fields.String(required=True, validate=validate.OneOf(PAYMENT_METHODS))
    payment_status = fields.String(load_default="paid", validate=validate.OneOf(PAYMENT_STATUSES))
    customer_id = fields.Integer(allow_none=True)
    notes = fields.String(allow_none=True)

    details = fields.List(
        fields.Nested(SaleLineSchema),
        required=True,
        validate=validate.Length(min=1, max=100),
    )

    # Server-computed
    receipt_number = fields.String(dump_only=True)
    total_amount = _Money(dump_only=True)
    tax_amount = _Money(dump_only=True)
    discount_amount = _Money(dump_only=True)
    subtotal = fields.Float(dump_only=True)
    item_count = fields.Integer(dump_only=True)
    staff_id = fields.Integer(dump_only=True)
    customer_name = fields.Method("_dump_customer_name", dump_only=True)
    staff_name = fields.Method("_dump_staff_name", dump_only=True)
    created_at = fields.DateTime(dump_only=True)

    def _dump_customer_name(self, obj):
        customer = getattr(obj, "customer", None)
        return customer.name if customer else None

    def _dump_staff_name(self, obj):
        staff = getattr(obj, "staff", None)
        return staff.name if staff else None

    @validates_schema
    def _reject_duplicate_parts(self, data, **kwargs):
        """A sale stores one row per (sale, part).

        ``SaleDetail`` has a composite primary key of ``(sale_id, part_id)``,
        so the same part twice in one payload would collide on insert. Reject
        it up front with a clear message rather than a database error.
        """
        details = data.get("details") or []
        part_ids = [line.get("part_id") for line in details]
        duplicates = {pid for pid in part_ids if part_ids.count(pid) > 1}
        if duplicates:
            raise ValidationError(
                {
                    "details": [
                        "Each part may only appear once per sale; combine the "
                        f"quantities instead. Duplicated part ids: {sorted(duplicates)}"
                    ]
                }
            )


class SaleDumpSchema(SaleSchema):
    """Sale serialisation including its line items."""

    details = fields.List(fields.Nested(SaleDetailSchema), dump_only=True)


class PaymentSchema(_BaseSchema):
    id = fields.Integer(dump_only=True)
    sale_id = fields.Integer(dump_only=True)
    amount = _Money(required=True, validate=validate.Range(min=Decimal("0.01")))
    payment_method = fields.String(required=True, validate=validate.OneOf(PAYMENT_METHODS))
    reference_number = fields.String(allow_none=True, validate=validate.Length(max=100))
    notes = fields.String(allow_none=True)
    payment_date = fields.DateTime(dump_only=True)


class VoidSaleSchema(_BaseSchema):
    reason = fields.String(required=True, validate=validate.Length(min=3, max=500))


# ============================================================
# OPERATIONS
# ============================================================
PO_STATUSES = ("pending", "ordered", "partial", "received", "cancelled")


class PurchaseOrderItemSchema(_BaseSchema):
    id = fields.Integer(dump_only=True)
    part_id = fields.Integer(required=True)
    quantity = fields.Integer(required=True, validate=validate.Range(min=1))
    unit_price = _Money(required=True, validate=validate.Range(min=Decimal("0")))
    discount_percent = _Money(load_default=Decimal("0"))
    tax_percent = _Money(load_default=Decimal("0"))
    notes = fields.String(allow_none=True)

    received_quantity = fields.Integer(dump_only=True)
    pending_quantity = fields.Integer(dump_only=True)
    discount_amount = _Money(dump_only=True)
    tax_amount = _Money(dump_only=True)
    line_total = _Money(dump_only=True)
    is_fully_received = fields.Boolean(dump_only=True)


class PurchaseOrderSchema(_BaseSchema):
    id = fields.Integer(dump_only=True)
    supplier_id = fields.Integer(required=True)
    expected_date = fields.DateTime(allow_none=True)
    status = fields.String(load_default="pending", validate=validate.OneOf(PO_STATUSES))
    shipping_cost = _Money(load_default=Decimal("0"), validate=validate.Range(min=Decimal("0")))
    notes = fields.String(allow_none=True)

    items = fields.List(
        fields.Nested(PurchaseOrderItemSchema),
        required=True,
        validate=validate.Length(min=1),
    )

    order_number = fields.String(dump_only=True)
    order_date = fields.DateTime(dump_only=True)
    received_date = fields.DateTime(dump_only=True)
    subtotal = _Money(dump_only=True)
    tax_amount = _Money(dump_only=True)
    total_amount = _Money(dump_only=True)
    created_at = fields.DateTime(dump_only=True)


class ReceiveLineSchema(_BaseSchema):
    """One line of a goods receipt against a purchase order."""

    part_id = fields.Integer(required=True)
    quantity = fields.Integer(required=True, validate=validate.Range(min=1))


class ReceiveItemsSchema(_BaseSchema):
    items = fields.List(
        fields.Nested(ReceiveLineSchema),
        required=True,
        validate=validate.Length(min=1),
    )

    @validates_schema
    def _reject_duplicate_parts(self, data, **kwargs):
        part_ids = [line.get("part_id") for line in data.get("items") or []]
        duplicates = {pid for pid in part_ids if part_ids.count(pid) > 1}
        if duplicates:
            raise ValidationError(
                {
                    "items": [
                        "Each part may only appear once per receipt; combine "
                        f"the quantities instead. Duplicated: {sorted(duplicates)}"
                    ]
                }
            )


EXPENSE_CATEGORIES = (
    "rent",
    "utilities",
    "supplies",
    "maintenance",
    "marketing",
    "salaries",
    "other",
)


class ExpenseSchema(_BaseSchema):
    id = fields.Integer(dump_only=True)
    expense_date = fields.DateTime(allow_none=True)
    category = fields.String(required=True, validate=validate.OneOf(EXPENSE_CATEGORIES))
    description = fields.String(required=True, validate=validate.Length(min=1))
    amount = _Money(required=True, validate=validate.Range(min=Decimal("0.01")))
    tax_amount = _Money(load_default=Decimal("0"), validate=validate.Range(min=Decimal("0")))
    payment_method = fields.String(required=True, validate=validate.OneOf(PAYMENT_METHODS))
    receipt_number = fields.String(allow_none=True, validate=validate.Length(max=100))
    vendor = fields.String(allow_none=True, validate=validate.Length(max=100))
    is_recurring = fields.Boolean(load_default=False)
    recurring_frequency = fields.String(
        allow_none=True, validate=validate.OneOf(("monthly", "quarterly", "yearly"))
    )
    notes = fields.String(allow_none=True)
    created_at = fields.DateTime(dump_only=True)


MAINTENANCE_TYPES = ("preventive", "corrective", "emergency", "inspection")


class MaintenanceLogSchema(_BaseSchema):
    id = fields.Integer(dump_only=True)
    part_id = fields.Integer(allow_none=True)
    equipment_name = fields.String(required=True, validate=validate.Length(min=1, max=100))
    equipment_serial = fields.String(allow_none=True, validate=validate.Length(max=100))
    maintenance_date = fields.DateTime(allow_none=True)
    maintenance_type = fields.String(required=True, validate=validate.OneOf(MAINTENANCE_TYPES))
    description = fields.String(required=True, validate=validate.Length(min=1))
    cost = _Money(load_default=Decimal("0"), validate=validate.Range(min=Decimal("0")))
    performed_by = fields.String(allow_none=True, validate=validate.Length(max=100))
    vendor = fields.String(allow_none=True, validate=validate.Length(max=100))
    parts_used = fields.String(allow_none=True)
    next_maintenance = fields.DateTime(allow_none=True)
    notes = fields.String(allow_none=True)

    is_overdue = fields.Boolean(dump_only=True)
    created_at = fields.DateTime(dump_only=True)


# ============================================================
# SYSTEM
# ============================================================
SETTING_TYPES = ("string", "number", "integer", "boolean", "json", "password")


class SettingsSchema(_BaseSchema):
    id = fields.Integer(dump_only=True)
    category = fields.String(required=True, validate=validate.Length(min=1, max=50))
    setting_key = fields.String(required=True, validate=validate.Length(min=1, max=100))
    setting_value = fields.String(allow_none=True)
    setting_type = fields.String(load_default="string", validate=validate.OneOf(SETTING_TYPES))
    description = fields.String(allow_none=True)
    is_public = fields.Boolean(load_default=False)
    is_required = fields.Boolean(load_default=False)
    updated_at = fields.DateTime(dump_only=True)
    updated_by = fields.Integer(dump_only=True)


NOTIFICATION_TYPES = ("info", "warning", "error", "success")


class NotificationSchema(_BaseSchema):
    id = fields.Integer(dump_only=True)
    user_id = fields.Integer(dump_only=True)
    title = fields.String(required=True, validate=validate.Length(min=1, max=200))
    message = fields.String(required=True, validate=validate.Length(min=1))
    type = fields.String(load_default="info", validate=validate.OneOf(NOTIFICATION_TYPES))
    category = fields.String(load_default="system", validate=validate.Length(max=50))
    action_url = fields.String(allow_none=True, validate=validate.Length(max=500))
    action_text = fields.String(allow_none=True, validate=validate.Length(max=100))
    priority = fields.Integer(load_default=0)

    is_read = fields.Boolean(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    read_at = fields.DateTime(dump_only=True)


class LoginSchema(_BaseSchema):
    email = fields.String(required=True, validate=validate.Length(min=1, max=100))
    password = fields.String(required=True, validate=validate.Length(min=1, max=200))
    remember = fields.Boolean(load_default=False)


class ChangePasswordSchema(_BaseSchema):
    current_password = fields.String(required=True)
    new_password = fields.String(required=True, validate=validate.Length(min=8, max=200))


# ============================================================
# SHARED INSTANCES
# ============================================================
user_schema = UserSchema()
users_schema = UserSchema(many=True)

part_schema = PartSchema()
parts_schema = PartSchema(many=True)

supplier_schema = SupplierSchema()
suppliers_schema = SupplierSchema(many=True)

stock_entry_schema = StockEntrySchema()
stock_entries_schema = StockEntrySchema(many=True)

customer_schema = CustomerSchema()
customers_schema = CustomerSchema(many=True)

sale_detail_schema = SaleDetailSchema()
sale_details_schema = SaleDetailSchema(many=True)

sale_schema = SaleDumpSchema()
sales_schema = SaleDumpSchema(many=True)
sale_create_schema = SaleSchema()

payment_schema = PaymentSchema()
payments_schema = PaymentSchema(many=True)

purchase_order_item_schema = PurchaseOrderItemSchema()
purchase_order_items_schema = PurchaseOrderItemSchema(many=True)

purchase_order_schema = PurchaseOrderSchema()
purchase_orders_schema = PurchaseOrderSchema(many=True)

expense_schema = ExpenseSchema()
expenses_schema = ExpenseSchema(many=True)

maintenance_log_schema = MaintenanceLogSchema()
maintenance_logs_schema = MaintenanceLogSchema(many=True)

settings_schema = SettingsSchema()
settings_schemas = SettingsSchema(many=True)

notification_schema = NotificationSchema()
notifications_schema = NotificationSchema(many=True)
