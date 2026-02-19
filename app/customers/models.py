from datetime import datetime
from decimal import Decimal
from app import db

class Customer(db.Model):
    __tablename__ = 'customers'

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(100), nullable=False)
    phone      = db.Column(db.String(20), unique=True, nullable=False, index=True)
    email      = db.Column(db.String(120), nullable=True)
    points     = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship to sales will be defined via backref in Sale model or here if Sale imported
    # We'll rely on the foreign key in Sale (added via migration/model update)

    def __repr__(self):
        return f"<Customer {self.name} ({self.phone}) Pts:{self.points}>"

class GiftCard(db.Model):
    __tablename__ = 'gift_cards'

    id              = db.Column(db.Integer, primary_key=True)
    code            = db.Column(db.String(50), unique=True, nullable=False, index=True)
    initial_balance = db.Column(db.Numeric(10, 2), nullable=False)
    balance         = db.Column(db.Numeric(10, 2), nullable=False)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
    is_active       = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f"<GiftCard {self.code} Bal: {self.balance}>"
