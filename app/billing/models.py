from datetime import datetime
from decimal import Decimal
from app import db


class InvoiceSequence(db.Model):
    """
    One row per calendar year — holds the last-used invoice sequence number.

    Why a dedicated table instead of COUNT(sales)?
    ─────────────────────────────────────────────
    COUNT(sales) inside a transaction is NOT safe under concurrent writes:

        Tx A: COUNT = 15  →  next = 16   ┐
        Tx B: COUNT = 15  →  next = 16   ┘  ← both generate 2026-0016

    One of them will crash on the UNIQUE constraint and roll back the entire
    sale — a terrible user experience.

    With this table + SELECT FOR UPDATE:

        Tx A: locks row, reads last_seq=15, writes 16, commits  ┐ serialised
        Tx B: blocks until Tx A commits, reads last_seq=16, writes 17 ┘

    No collision. No rollback. No lost sale.
    """
    __tablename__ = 'invoice_sequences'

    year     = db.Column(db.Integer, primary_key=True)   # e.g. 2026
    last_seq = db.Column(db.Integer, nullable=False, default=0)

    def __repr__(self):
        return f"<InvoiceSequence year={self.year} last_seq={self.last_seq}>"




class Sale(db.Model):
    """
    Represents one completed billing transaction (one invoice).
    A Sale has many SaleItems.
    """
    __tablename__ = 'sales'

    id             = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(20), unique=True, nullable=False, index=True)
    cashier_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    total_amount   = db.Column(db.Numeric(12, 2), nullable=False)  # sum of subtotals (excl. GST)
    gst_total      = db.Column(db.Numeric(12, 2), nullable=False)  # sum of GST amounts
    payment_method = db.Column(db.String(20), nullable=False, default='cash')
    created_at     = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # ── Relationships ─────────────────────────────────────────────
    cashier = db.relationship('User',     backref='sales', lazy='select')
    items   = db.relationship('SaleItem', backref='sale',  lazy='select',
                              cascade='all, delete-orphan')

    # ── Computed helpers ──────────────────────────────────────────
    @property
    def grand_total(self) -> Decimal:
        """total_amount + gst_total, as Decimal."""
        return Decimal(str(self.total_amount)) + Decimal(str(self.gst_total))

    def __repr__(self):
        return f"<Sale {self.invoice_number!r} ₹{self.grand_total}>"


class SaleItem(db.Model):
    """
    One line item inside a Sale.
    Stores a snapshot of price and GST at the time of sale —
    so future product edits don't alter historical invoices.
    """
    __tablename__ = 'sale_items'

    id            = db.Column(db.Integer, primary_key=True)
    sale_id       = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False)
    product_id    = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity      = db.Column(db.Integer, nullable=False)
    price_at_sale = db.Column(db.Numeric(10, 2), nullable=False)  # base price snapshot
    gst_percent   = db.Column(db.Integer, nullable=False)
    subtotal      = db.Column(db.Numeric(12, 2), nullable=False)  # qty × price_at_sale

    # ── Relationship ──────────────────────────────────────────────
    product = db.relationship('Product', lazy='select')

    # ── Computed helpers ──────────────────────────────────────────
    @property
    def gst_amount(self) -> Decimal:
        """GST rupee amount for this line item."""
        return (Decimal(str(self.subtotal)) *
                Decimal(str(self.gst_percent)) / Decimal('100')).quantize(Decimal('0.01'))

    @property
    def subtotal_with_gst(self) -> Decimal:
        """subtotal + gst_amount for this line."""
        return Decimal(str(self.subtotal)) + self.gst_amount

    def __repr__(self):
        return f"<SaleItem sale={self.sale_id} product={self.product_id} qty={self.quantity}>"


class CashSession(db.Model):
    """
    Tracks a cashier's shift/session — opening balance vs closing total.
    """
    __tablename__ = 'cash_sessions'

    id           = db.Column(db.Integer, primary_key=True)
    cashier_id   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    opening_cash = db.Column(db.Numeric(10, 2), nullable=False)
    
    # Running total of all sales in this session (incremented on billing complete)
    system_total = db.Column(db.Numeric(12, 2), nullable=False, default=0.00)
    
    closing_cash = db.Column(db.Numeric(10, 2), nullable=True)
    start_time   = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    end_time     = db.Column(db.DateTime, nullable=True)

    # ── Relationships ─────────────────────────────────────────────
    # user backref serves as access to cashier details
    cashier = db.relationship('User', backref=db.backref('sessions', lazy='dynamic'))

    @property
    def is_active(self):
        return self.end_time is None

    @property
    def discrepancy(self):
        """Difference between (opening + sales) and closing cash."""
        if self.closing_cash is None:
            return None
        expected = Decimal(str(self.opening_cash)) + Decimal(str(self.system_total))
        return Decimal(str(self.closing_cash)) - expected

    def __repr__(self):
        return f"<CashSession {self.id} Cashier:{self.cashier_id} Open:{self.opening_cash}>"
