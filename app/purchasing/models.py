"""
app/purchasing/models.py
------------------------
Models for the Supplier & Purchase Order system.

Tables:
  suppliers
  purchase_orders
  purchase_order_items
  goods_receipts
  goods_receipt_items
"""
import enum
from datetime import datetime, date
from typing import Optional

from app import db


# ── Status Enum ───────────────────────────────────────────────────

class POStatus(enum.Enum):
    DRAFT     = 'DRAFT'
    SENT      = 'SENT'
    PARTIAL   = 'PARTIAL'
    RECEIVED  = 'RECEIVED'
    CANCELLED = 'CANCELLED'


# ── Supplier ──────────────────────────────────────────────────────

class Supplier(db.Model):
    """Vendor / supplier master record."""
    __tablename__ = 'suppliers'

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(200), nullable=False, index=True)
    contact    = db.Column(db.String(200), nullable=True)   # phone / email / person
    gst_no     = db.Column(db.String(20),  nullable=True)
    address    = db.Column(db.Text,        nullable=True)
    is_active  = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    purchase_orders = db.relationship('PurchaseOrder', backref='supplier', lazy='dynamic')

    def __repr__(self):
        return f'<Supplier {self.name!r}>'


# ── Purchase Order ────────────────────────────────────────────────

class PurchaseOrder(db.Model):
    """A purchase order placed with a supplier."""
    __tablename__ = 'purchase_orders'

    id            = db.Column(db.Integer, primary_key=True)
    supplier_id   = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False, index=True)
    status        = db.Column(db.Enum(POStatus), nullable=False, default=POStatus.DRAFT, index=True)
    created_by    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    expected_date = db.Column(db.Date, nullable=True)    # expected delivery date
    notes         = db.Column(db.Text, nullable=True)
    created_at    = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at    = db.Column(db.DateTime, nullable=False, default=datetime.utcnow,
                              onupdate=datetime.utcnow)

    # Relationships
    items    = db.relationship('PurchaseOrderItem', backref='purchase_order',
                               cascade='all, delete-orphan', lazy='select')
    receipts = db.relationship('GoodsReceipt', backref='purchase_order',
                               lazy='select')
    creator  = db.relationship('User', lazy='select', foreign_keys=[created_by])

    # ── Helpers ───────────────────────────────────────────────────
    @property
    def total_cost(self):
        """Sum of ordered_qty × unit_cost for all line items."""
        from decimal import Decimal
        return sum(
            (item.ordered_qty * item.unit_cost
             for item in self.items
             if item.unit_cost is not None),
            Decimal('0')
        )

    @property
    def is_overdue(self) -> bool:
        return (
            self.expected_date is not None
            and self.expected_date < date.today()
            and self.status in (POStatus.DRAFT, POStatus.SENT, POStatus.PARTIAL)
        )

    def __repr__(self):
        return f'<PO #{self.id} {self.status.value}>'


# ── Purchase Order Item ───────────────────────────────────────────

class PurchaseOrderItem(db.Model):
    """A single product line on a Purchase Order."""
    __tablename__ = 'purchase_order_items'

    id          = db.Column(db.Integer, primary_key=True)
    po_id       = db.Column(db.Integer, db.ForeignKey('purchase_orders.id', ondelete='CASCADE'),
                            nullable=False, index=True)
    product_id  = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    ordered_qty = db.Column(db.Integer, nullable=False)
    unit_cost   = db.Column(db.Numeric(10, 2), nullable=True)   # cost price per unit

    # Relationships
    product = db.relationship('Product', lazy='select')

    @property
    def total_received(self) -> int:
        """Sum of all received quantities across GRNs for this PO item."""
        return sum(
            ri.received_qty
            for grn in self.purchase_order.receipts
            for ri in grn.items
            if ri.po_item_id == self.id
        )

    @property
    def remaining_qty(self) -> int:
        return max(0, self.ordered_qty - self.total_received)

    def __repr__(self):
        return f'<POItem PO:{self.po_id} P:{self.product_id} qty:{self.ordered_qty}>'


# ── Goods Receipt (GRN) ───────────────────────────────────────────

class GoodsReceipt(db.Model):
    """A delivery received against a Purchase Order."""
    __tablename__ = 'goods_receipts'

    id            = db.Column(db.Integer, primary_key=True)
    po_id         = db.Column(db.Integer, db.ForeignKey('purchase_orders.id'), nullable=False, index=True)
    received_by   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    received_date = db.Column(db.Date, nullable=False, default=date.today)
    notes         = db.Column(db.Text, nullable=True)
    created_at    = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    items    = db.relationship('GoodsReceiptItem', backref='goods_receipt',
                               cascade='all, delete-orphan', lazy='select')
    receiver = db.relationship('User', lazy='select', foreign_keys=[received_by])

    def __repr__(self):
        return f'<GRN #{self.id} PO:{self.po_id}>'


# ── Goods Receipt Item ────────────────────────────────────────────

class GoodsReceiptItem(db.Model):
    """A single product line in a GRN."""
    __tablename__ = 'goods_receipt_items'

    id           = db.Column(db.Integer, primary_key=True)
    grn_id       = db.Column(db.Integer, db.ForeignKey('goods_receipts.id', ondelete='CASCADE'),
                             nullable=False, index=True)
    po_item_id   = db.Column(db.Integer, db.ForeignKey('purchase_order_items.id'), nullable=False)
    received_qty = db.Column(db.Integer, nullable=False)
    batch_number = db.Column(db.String(60), nullable=True)
    expiry_date  = db.Column(db.Date, nullable=True)

    # Relationship back to the PO item for easy product lookup
    po_item = db.relationship('PurchaseOrderItem', lazy='select')

    def __repr__(self):
        return f'<GRNItem GRN:{self.grn_id} POItem:{self.po_item_id} qty:{self.received_qty}>'
