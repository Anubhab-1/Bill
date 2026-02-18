from flask import Blueprint

billing = Blueprint('billing', __name__)

from app.billing import routes  # noqa: F401, E402
from app.billing import models  # noqa: F401, E402  — registers Sale/SaleItem with SQLAlchemy
