"""
app/promotions/models.py
------------------------
Promotion and AppliedPromotion models.

Promotion.params is a JSON-encoded dict whose schema depends on promo_type:
  percentage_item  → {"product_ids": [1, 2], "percent": 10}
  fixed_item       → {"product_ids": [3], "amount": 50}
  bill_percentage  → {"percent": 5}
  buy_x_get_y      → {"product_id": 4, "buy_qty": 2, "free_qty": 1}
"""
import json
from datetime import datetime, date
from app import db


PROMO_TYPES = [
    ('percentage_item',  '% Off Item(s)'),
    ('fixed_item',       'Fixed ₹ Off Item(s)'),
    ('bill_percentage',  '% Off Bill (Coupon)'),
    ('buy_x_get_y',      'Buy X Get Y Free (BOGOF)'),
]
PROMO_TYPE_CHOICES = [p[0] for p in PROMO_TYPES]


class Promotion(db.Model):
    """A configurable discount rule."""
    __tablename__ = 'promotions'

    id           = db.Column(db.Integer, primary_key=True)
    name         = db.Column(db.String(200), nullable=False)
    promo_type   = db.Column(db.String(30),  nullable=False)   # see PROMO_TYPE_CHOICES
    params       = db.Column(db.Text,        nullable=False, default='{}')   # JSON string
    start_date   = db.Column(db.Date,        nullable=True)    # None = always eligible
    end_date     = db.Column(db.Date,        nullable=True)    # None = never expires
    is_active    = db.Column(db.Boolean,     nullable=False, default=True)
    max_uses     = db.Column(db.Integer,     nullable=True)    # None = unlimited
    current_uses = db.Column(db.Integer,     nullable=False, default=0)
    stackable    = db.Column(db.Boolean,     nullable=False, default=True)
    created_by   = db.Column(db.Integer,     db.ForeignKey('users.id'), nullable=True)
    created_at   = db.Column(db.DateTime,    nullable=False, default=datetime.utcnow)

    # Relationships
    applied      = db.relationship('AppliedPromotion', backref='promotion', lazy='dynamic')
    creator      = db.relationship('User', lazy='select', foreign_keys=[created_by])

    # ── Helpers ───────────────────────────────────────────────────

    @property
    def params_dict(self) -> dict:
        try:
            return json.loads(self.params or '{}')
        except (ValueError, TypeError):
            return {}

    @params_dict.setter
    def params_dict(self, value: dict):
        self.params = json.dumps(value)

    @property
    def is_valid_today(self) -> bool:
        """True if the promotion is active and within its date range."""
        if not self.is_active:
            return False
        if self.max_uses is not None and self.current_uses >= self.max_uses:
            return False
        today = date.today()
        if self.start_date and today < self.start_date:
            return False
        if self.end_date and today > self.end_date:
            return False
        return True

    @property
    def type_label(self) -> str:
        return dict(PROMO_TYPES).get(self.promo_type, self.promo_type)

    def __repr__(self):
        return f'<Promotion {self.name!r} {self.promo_type}>'


class AppliedPromotion(db.Model):
    """
    Records a promotion that was applied to a completed Sale.
    Stores a snapshot of the promo name so historical records survive
    even if the Promotion row is later deleted or renamed.
    """
    __tablename__ = 'applied_promotions'

    id              = db.Column(db.Integer, primary_key=True)
    sale_id         = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False, index=True)
    promotion_id    = db.Column(db.Integer, db.ForeignKey('promotions.id'), nullable=True)
    promo_name      = db.Column(db.String(200), nullable=False)   # snapshot
    discount_amount = db.Column(db.Numeric(12, 2), nullable=False)
    description     = db.Column(db.String(300), nullable=True)    # e.g. "10% off Basmati Rice"

    # Relationship
    sale = db.relationship('Sale', backref=db.backref('applied_promotions', lazy='select'))

    def __repr__(self):
        return f'<AppliedPromo sale={self.sale_id} promo={self.promo_name!r} disc={self.discount_amount}>'
