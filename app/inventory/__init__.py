from flask import Blueprint

inventory = Blueprint('inventory', __name__)

from app.inventory import routes  # noqa: F401, E402
from app.inventory import models  # noqa: F401, E402  — registers Product with SQLAlchemy
