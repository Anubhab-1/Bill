"""
app/purchasing/__init__.py
--------------------------
Purchasing & Procurement blueprint.
URL prefix: /purchasing
"""
from flask import Blueprint

purchasing = Blueprint('purchasing', __name__)

from app.purchasing import routes  # noqa: E402, F401  (registers routes)
