"""
app/promotions/__init__.py
--------------------------
Promotions & Pricing Rules blueprint.
URL prefix: /promotions
"""
from flask import Blueprint

promotions = Blueprint('promotions', __name__)

from app.promotions import routes  # noqa: E402, F401
