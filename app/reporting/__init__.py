"""
app/reporting/__init__.py
-------------------------
Reporting & Analytics blueprint.
URL prefix: /reporting
"""
from flask import Blueprint

reporting = Blueprint('reporting', __name__)

from app.reporting import routes  # noqa: E402, F401
