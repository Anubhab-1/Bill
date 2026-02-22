from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from app import db


class InvoiceSequence(db.Model):
    __tablename__ = 'invoice_sequences'

    year = db.Column(db.Integer, primary_key=True)
    last_seq = db.Column(db.Integer, nullable=False, default=0)

    def __repr__(self):
        return f"<InvoiceSequence year={self.year} last_seq={self.last_seq}>"


class Sale(db.Model):
    __tablename__ = 'sales'
    __table_args__ = (
        db.CheckConstraint('total_amount >= 0', name='check_sale_total_amount_non_negative'),
        db.CheckConstraint('gst_total >= 0', name='check_sale_gst_total_non_negative'),
        db.CheckConstraint('discount_amount >= 0', name='check_sale_discount_amount_non_negative'),
        db.CheckConstraint('discount_percent >= 0 AND discount_percent <= 100', name='check_sale_discount_percent_range'),
        db.CheckConstraint('grand_total IS NULL OR grand_total >= 0', name='check_sale_grand_total_non_negative'),
    )

    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(20), unique=True, nullable=False, index=True)
    cashier_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True)
    total_amount = db.Column(db.Numeric(12, 2), nullable=False)
    discount_percent = db.Column(db.Numeric(5, 2), nullable=False, default=0)
    discount_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    gst_total = db.Column(db.Numeric(12, 2), nullable=False)
    grand_total = db.Column(db.Numeric(10, 2))
    payment_method = db.Column(db.String(20), nullable=False, default='cash')
    print_html = db.Column(db.Text)
    is_printed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    cashier = db.relationship('User', backref='sales', lazy='select')
    customer = db.relationship('Customer', backref='sales', lazy='select')
    items = db.relationship(
        'SaleItem',
        backref='sale',
        lazy='select',
        cascade='all, delete-orphan',
    )

    @property
    def computed_grand_total(self) -> Decimal:
        if self.grand_total is not None:
            return Decimal(str(self.grand_total))
        return (Decimal(str(self.total_amount)) + Decimal(str(self.gst_total))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def __repr__(self):
        return f"<Sale {self.invoice_number!r} {self.computed_grand_total}>"


class SaleItem(db.Model):
    __tablename__ = 'sale_items'
    __table_args__ = (
        db.CheckConstraint('quantity > 0', name='check_sale_item_quantity_positive'),
        db.CheckConstraint('subtotal >= 0', name='check_sale_item_subtotal_non_negative'),
    )

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id'), nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False)
    price_at_sale = db.Column(db.Numeric(10, 2), nullable=False)
    snapshot_size = db.Column(db.String(10), nullable=False)
    snapshot_color = db.Column(db.String(50), nullable=False)
    gst_percent = db.Column(db.Integer, nullable=False)
    subtotal = db.Column(db.Numeric(12, 2), nullable=False)
    weight_kg = db.Column(db.Numeric(8, 3), nullable=True)
    unit_label = db.Column(db.String(10), nullable=True)

    variant = db.relationship('ProductVariant', lazy='select')

    @property
    def product(self):
        return self.variant.product if self.variant else None

    @property
    def gst_amount(self) -> Decimal:
        return (
            Decimal(str(self.subtotal)) * Decimal(str(self.gst_percent)) / Decimal('100')
        ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @property
    def subtotal_with_gst(self) -> Decimal:
        return Decimal(str(self.subtotal)) + self.gst_amount

    def __repr__(self):
        return f"<SaleItem sale={self.sale_id} variant={self.variant_id} qty={self.quantity}>"


class Return(db.Model):
    __tablename__ = 'returns'
    __table_args__ = (
        db.CheckConstraint('total_refunded >= 0', name='check_return_total_refunded_non_negative'),
    )

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False)
    processed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    refund_method = db.Column(db.String(20), nullable=False)
    total_refunded = db.Column(db.Numeric(12, 2), nullable=False)
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    sale = db.relationship('Sale', backref='returns', lazy='select')
    cashier = db.relationship('User', lazy='select')
    items = db.relationship(
        'ReturnItem',
        backref='return_obj',
        lazy='select',
        cascade='all, delete-orphan',
    )


class ReturnItem(db.Model):
    __tablename__ = 'return_items'
    __table_args__ = (
        db.CheckConstraint('quantity > 0', name='check_return_item_quantity_positive'),
        db.CheckConstraint('refund_amount >= 0', name='check_return_item_refund_amount_non_negative'),
    )

    id = db.Column(db.Integer, primary_key=True)
    return_id = db.Column(db.Integer, db.ForeignKey('returns.id'), nullable=False)
    sale_item_id = db.Column(db.Integer, db.ForeignKey('sale_items.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    refund_amount = db.Column(db.Numeric(12, 2), nullable=False)
    reason = db.Column(db.String(100))

    product = db.relationship('Product', lazy='select')
    sale_item = db.relationship('SaleItem', backref='return_items', lazy='select')


class SalePayment(db.Model):
    __tablename__ = 'sale_payments'
    __table_args__ = (
        db.CheckConstraint('amount >= 0', name='check_sale_payment_amount_non_negative'),
    )

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False)
    payment_method = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    reference = db.Column(db.String(100))

    sale = db.relationship('Sale', backref='payments', lazy='select')


class CashSession(db.Model):
    __tablename__ = 'cash_sessions'
    __table_args__ = (
        db.CheckConstraint('opening_cash >= 0', name='check_cash_session_opening_non_negative'),
        db.CheckConstraint('system_total >= 0', name='check_cash_session_system_total_non_negative'),
        db.CheckConstraint('closing_cash IS NULL OR closing_cash >= 0', name='check_cash_session_closing_non_negative'),
    )

    id = db.Column(db.Integer, primary_key=True)
    cashier_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    opening_cash = db.Column(db.Numeric(10, 2), nullable=False)
    system_total = db.Column(db.Numeric(12, 2), nullable=False, default=0.00)
    closing_cash = db.Column(db.Numeric(10, 2), nullable=True)
    closing_notes = db.Column(db.String(255), nullable=True)
    start_time = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    end_time = db.Column(db.DateTime, nullable=True)

    cashier = db.relationship('User', backref=db.backref('sessions', lazy='dynamic'))

    @property
    def is_active(self):
        return self.end_time is None

    @property
    def discrepancy(self):
        if self.closing_cash is None:
            return None
        expected = Decimal(str(self.opening_cash)) + Decimal(str(self.system_total))
        return Decimal(str(self.closing_cash)) - expected

    def __repr__(self):
        return f"<CashSession {self.id} Cashier:{self.cashier_id} Open:{self.opening_cash}>"
