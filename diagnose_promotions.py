import os
import sys
from app import create_app, db

os.environ["SECRET_KEY"] = "temp-verify-key"
os.environ["DATABASE_URL"] = "postgresql://postgres:Galaxy%402006@localhost:5432/mall"

app = create_app('development')
client = app.test_client()

with client.session_transaction() as sess:
    sess['user_id'] = 1
    sess['role'] = 'admin'

try:
    response = client.get('/promotions/new')
    print(f"Status Code: {response.status_code}")
    if response.status_code == 500:
        # To get the actual error, we can use app.handle_exception
        # But let's just try to run the code that create() runs manually
        from app.promotions.routes import create
        # We need a request context
        with app.test_request_context('/promotions/new'):
            from app.auth.models import User
            # Mock the admin check if needed, but create() just needs to run its logic
            # Let's try to just call the view function logic
            from app.inventory.models import Product
            products = Product.query.filter_by(is_active=True).order_by(Product.name).all()
            from flask import render_template
            # This might fail if some global is missing
            try:
                # Manually run the query and template render
                errors = {}
                from app.promotions.models import PROMO_TYPES
                # render_template('promotions/form.html', ...)
                # If this fails, it's a template error
                print("Attempting manual query and render simulation...")
                from flask import g
                g.user = db.session.get(User, 1)
                
                # Try just the query first
                print(f"Products count: {len(products)}")
                
                # Try the template
                html = render_template('promotions/form.html', title='New Promotion', errors=errors, products=products)
                print("Manual render successful.")
            except Exception as e:
                import traceback
                traceback.print_exc()
    else:
        print("Success or other status.")
except Exception as e:
    import traceback
    traceback.print_exc()
