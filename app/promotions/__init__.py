from flask import Blueprint

promotions = Blueprint('promotions', __name__)

@promotions.app_context_processor
def inject_promotions_context():
    from app.promotions.models import PROMO_TYPES
    return {
        'promo_types': dict(PROMO_TYPES),
        'promo_types_list': PROMO_TYPES
    }

from app.promotions import routes  # noqa: E402, F401
