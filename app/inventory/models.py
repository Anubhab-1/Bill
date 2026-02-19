from decimal import Decimal
from datetime import datetime, date
from typing import Optional
from app import db

# ── Central threshold — change here, applies everywhere ──────────
LOW_STOCK_THRESHOLD = 5


class Product(db.Model):
    """Represents a product in the mall inventory."""
    __tablename__ = 'products'

    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(200), nullable=False, index=True)
    barcode     = db.Column(db.String(100), unique=True, nullable=False, index=True)
    price       = db.Column(db.Numeric(10, 2), nullable=False)   # stored as NUMERIC(10,2) in PG
    stock       = db.Column(db.Integer, nullable=False, default=0)
    gst_percent = db.Column(db.Integer, nullable=False, default=0)
    is_active   = db.Column(db.Boolean, nullable=False, default=True, index=True)
    # Weighed-item support
    is_weighed    = db.Column(db.Boolean, nullable=False, default=False)
    price_per_kg  = db.Column(db.Numeric(10, 2), nullable=True)   # set when is_weighed=True
    created_at  = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at  = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow   # auto-updated by SQLAlchemy on every UPDATE
    )

    __table_args__ = (
        db.CheckConstraint('stock >= 0', name='check_stock_non_negative'),
        db.CheckConstraint('price > 0', name='check_price_positive'),
        db.CheckConstraint('gst_percent >= 0 AND gst_percent <= 28', name='check_gst_valid'),
    )

    # ── Computed helpers ──────────────────────────────────────────
    @property
    def price_with_gst(self) -> Decimal:
        """
        Return price inclusive of GST as a Decimal (never float).
        Decimal arithmetic avoids floating-point rounding errors.
        """
        rate = Decimal(self.gst_percent) / Decimal(100)
        return (Decimal(str(self.price)) * (1 + rate)).quantize(Decimal('0.01'))

    @property
    def is_low_stock(self) -> bool:
        """True when stock is at or below LOW_STOCK_THRESHOLD."""
        return self.stock <= LOW_STOCK_THRESHOLD

    def __repr__(self):
        return f"<Product {self.barcode!r} {self.name!r}>"

    # ── Batch relationship (defined here to avoid SQLAlchemy MetaData conflicts) ──
    # Populated once ProductBatch is declared below; lazy='dynamic' lets us
    # apply .order_by() at query-time for FIFO ordering.
    # (Relationship added after class via back_populates pattern below)


class InventoryLog(db.Model):
    """
    Audit trail for stock changes.
    Tracks old vs new stock, who changed it, and why.
    """
    __tablename__ = 'inventory_logs'

    id          = db.Column(db.Integer, primary_key=True)
    product_id  = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    old_stock   = db.Column(db.Integer, nullable=False)
    new_stock   = db.Column(db.Integer, nullable=False)
    changed_by  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    reason      = db.Column(db.String(255), nullable=False)
    timestamp   = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    # ── Relationships ─────────────────────────────────────────────
    product = db.relationship('Product', backref=db.backref('logs', lazy='select'))
    user    = db.relationship('User', lazy='select')  # Relies on 'User' model (in auth/models.py) being loaded

    def __repr__(self):
        return f"<Log Product:{self.product_id} {self.old_stock}->{self.new_stock} ({self.reason})>"


class ProductBatch(db.Model):
    """
    Tracks individual stock batches for a product.
    Supports expiry dates and FIFO deduction during billing.
    """
    __tablename__ = 'product_batches'

    id           = db.Column(db.Integer, primary_key=True)
    product_id   = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False, index=True)
    batch_number = db.Column(db.String(60), nullable=False, default='LEGACY')
    expiry_date  = db.Column(db.Date, nullable=True)         # NULL = no expiry (non-perishable)
    quantity     = db.Column(db.Integer, nullable=False, default=0)
    cost_price   = db.Column(db.Numeric(10, 2), nullable=True)
    created_at   = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # The 'product' relationship is now defined via backref from Product.batches

    __table_args__ = (
        db.CheckConstraint('quantity >= 0', name='check_batch_qty_non_negative'),
    )

    # ── Computed helpers ──────────────────────────────────────────
    @property
    def is_expired(self) -> bool:
        return self.expiry_date is not None and self.expiry_date < date.today()

    @property
    def days_to_expiry(self) -> Optional[int]:
        if self.expiry_date is None:
            return None
        return (self.expiry_date - date.today()).days

    def __repr__(self):
        return f"<Batch {self.batch_number!r} P:{self.product_id} qty:{self.quantity} exp:{self.expiry_date}>"
