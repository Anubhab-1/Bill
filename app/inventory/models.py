from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.hybrid import hybrid_property

from app import db


LOW_STOCK_THRESHOLD = 5


class Product(db.Model):
    __tablename__ = 'products'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, index=True)
    barcode = db.Column(db.String(100), unique=True, nullable=False, index=True)
    brand = db.Column(db.String(100), nullable=True)
    category = db.Column(db.String(100), nullable=True)
    description = db.Column(db.Text, nullable=True)
    gst_percent = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    is_weighed = db.Column(db.Boolean, nullable=False, default=False)
    price_per_kg = db.Column(db.Numeric(10, 2), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    # Legacy data support: stock and price persisted at product level
    _legacy_stock = db.Column('stock', db.Integer, nullable=False, default=0)
    _legacy_price = db.Column('price', db.Numeric(10, 2), nullable=False, default=Decimal('0'))

    __table_args__ = (
        db.CheckConstraint('gst_percent >= 0 AND gst_percent <= 28', name='check_gst_valid'),
    )

    variants = db.relationship(
        'ProductVariant',
        backref='product',
        lazy=True,
        cascade='all, delete-orphan',
    )

    @property
    def total_stock(self) -> int:
        return sum(v.stock for v in self.variants if v.is_active)

    @hybrid_property
    def stock(self) -> int:
        if self.default_variant is None:
            return int(getattr(self, '_legacy_stock', 0) or 0)
        return self.total_stock

    @stock.expression
    def stock(cls):
        return (
            select(func.coalesce(func.sum(ProductVariant.stock), 0))
            .where(
                ProductVariant.product_id == cls.id,
                ProductVariant.is_active.is_(True),
            )
            .correlate(cls)
            .scalar_subquery()
        )

    @stock.setter
    def stock(self, value):
        normalized = int(value or 0)
        if self.default_variant is None:
            self._legacy_stock = normalized
            return
        self.default_variant.stock = normalized

    @property
    def default_variant(self):
        active_variants = [v for v in self.variants if v.is_active]
        if not active_variants:
            return None
        return sorted(active_variants, key=lambda v: v.id)[0]

    @hybrid_property
    def price(self):
        if self.default_variant is None:
            return Decimal(str(getattr(self, '_legacy_price', Decimal('0'))))
        return self.default_variant.price

    @price.expression
    def price(cls):
        return (
            select(ProductVariant.price)
            .where(
                ProductVariant.product_id == cls.id,
                ProductVariant.is_active.is_(True),
            )
            .order_by(ProductVariant.id.asc())
            .limit(1)
            .correlate(cls)
            .scalar_subquery()
        )

    @price.setter
    def price(self, value):
        normalized = Decimal(str(value)) if value is not None else Decimal('0')
        if self.default_variant is None:
            self._legacy_price = normalized
            return
        self.default_variant.price = normalized

    @property
    def price_with_gst(self) -> Decimal:
        rate = Decimal(self.gst_percent) / Decimal(100)
        if self.is_weighed and self.price_per_kg is not None:
            base_price = Decimal(str(self.price_per_kg))
        elif self.default_variant is not None:
            base_price = Decimal(str(self.default_variant.price))
        else:
            base_price = Decimal('0')
        from decimal import ROUND_HALF_UP
        return (base_price * (Decimal('1') + rate)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @property
    def is_low_stock(self) -> bool:
        return self.total_stock <= LOW_STOCK_THRESHOLD

    def __repr__(self):
        return f"<Product {self.id} {self.name!r}>"


class ProductVariant(db.Model):
    __tablename__ = 'product_variants'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(
        db.Integer,
        db.ForeignKey('products.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    size = db.Column(db.String(10), nullable=False)
    color = db.Column(db.String(50), nullable=False)
    sku = db.Column(db.String(100), nullable=True)
    barcode = db.Column(db.String(100), nullable=False, unique=True, index=True)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    stock = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    __table_args__ = (
        db.CheckConstraint('stock >= 0', name='check_variant_stock_non_negative'),
        db.CheckConstraint('price > 0', name='check_variant_price_positive'),
    )

    def __repr__(self):
        return f"<ProductVariant {self.id} P:{self.product_id} {self.size}/{self.color}>"


class InventoryLog(db.Model):
    __tablename__ = 'inventory_logs'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    old_stock = db.Column(db.Integer, nullable=False)
    new_stock = db.Column(db.Integer, nullable=False)
    changed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    reason = db.Column(db.String(255), nullable=False)
    reference = db.Column(db.Integer, nullable=True, index=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    product = db.relationship('Product', backref=db.backref('logs', lazy='select'))
    user = db.relationship('User', lazy='select')

    def __repr__(self):
        return f"<Log Product:{self.product_id} {self.old_stock}->{self.new_stock} ({self.reason})>"


class ProductBatch(db.Model):
    __tablename__ = 'product_batches'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(
        db.Integer,
        db.ForeignKey('products.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    batch_number = db.Column(db.String(60), nullable=False, default='LEGACY')
    expiry_date = db.Column(db.Date, nullable=True)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    cost_price = db.Column(db.Numeric(10, 2), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        db.CheckConstraint('quantity >= 0', name='check_batch_qty_non_negative'),
    )

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
