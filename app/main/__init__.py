from flask import Blueprint

main = Blueprint('main', __name__)

from app.main import routes  # noqa: F401, E402
