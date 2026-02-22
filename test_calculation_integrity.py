import os
import pytest
from decimal import Decimal
from app import create_app, db
from app.inventory.models import Product, ProductVariant
from app.promotions.models import Promotion, AppliedPromotion
from app.billing.models import Sale, SaleItem, CashSession
from app.auth.models import User

@pytest.fixture
def app():
    os.environ["SECRET_KEY"] = "test-secret"
    os.environ["DATABASE_URL"] = "postgresql://postgres:Galaxy%402006@localhost:5432/mall"
    app = create_app('testing')
    app.config['WTF_CSRF_ENABLED'] = False
    from app.billing.models import SalePayment
    from app.inventory.models import InventoryLog, Product, ProductVariant
    with app.app_context():
        # Clean up relevant tables
        db.session.query(AppliedPromotion).delete()
        db.session.query(SaleItem).delete()
        db.session.query(SalePayment).delete()
        db.session.query(InventoryLog).delete()
        db.session.query(CashSession).delete()
        db.session.query(Sale).delete()
        db.session.query(Promotion).delete()
        db.session.query(ProductVariant).delete()
        db.session.query(Product).delete()
        db.session.commit()
    return app

@pytest.fixture
def client(app):
    return app.test_client()

def test_promotion_and_discount_persistence(app, client):
    with app.app_context():
        # 1. Setup Data
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(username='admin', name='Administrator', role='admin')
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()

        p1 = Product(name="Test Product 1", barcode="TP001", gst_percent=5, is_active=True)
        db.session.add(p1)
        db.session.flush()
        v1 = ProductVariant(product_id=p1.id, size="M", color="Red", barcode="TP001-M", price=Decimal('100.00'), stock=10)
        db.session.add(v1)

        p2 = Product(name="Test Product 2", barcode="TP002", gst_percent=12, is_active=True)
        db.session.add(p2)
        db.session.flush()
        v2 = ProductVariant(product_id=p2.id, size="L", color="Blue", barcode="TP002-L", price=Decimal('200.00'), stock=10)
        db.session.add(v2)

        # Create a 10% bill discount promo
        promo = Promotion(
            name="10% Off Bill",
            promo_type='bill_percentage',
            is_active=True,
            stackable=True
        )
        promo.params_dict = {"percent": 10}
        db.session.add(promo)
        db.session.commit()

        # 2. Login & Open Session
        with open("test_debug.log", "w", encoding="utf-8") as f_log:
            f_log.write("=== START TEST ===\n")
            
            # Real Login
            login_resp = client.post('/auth/login', data={
                'username': 'admin',
                'password': 'admin123'
            }, follow_redirects=True)
            f_log.write(f"LOGIN STATUS: {login_resp.status_code}\n")
            f_log.write(f"LOGIN URL: {login_resp.request.url}\n")
            
            # Open Cash Session
            session_resp = client.post('/billing/session/open', data={
                'opening_cash': '500.00'
            }, follow_redirects=True)
            f_log.write(f"SESSION OPEN STATUS: {session_resp.status_code}\n")
            f_log.write(f"SESSION OPEN URL: {session_resp.request.url}\n")
            
            # 3. Add to cart
            r1 = client.post('/billing/add-item', data={'barcode': 'TP001-M'}, follow_redirects=True)
            f_log.write(f"ADD 1 STATUS: {r1.status_code}, URL: {r1.request.url}\n")
            r2 = client.post('/billing/add-item', data={'barcode': 'TP001-M'}, follow_redirects=True)
            f_log.write(f"ADD 2 STATUS: {r2.status_code}, URL: {r2.request.url}\n")
            r3 = client.post('/billing/add-item', data={'barcode': 'TP002-L'}, follow_redirects=True)
            f_log.write(f"ADD 3 STATUS: {r3.status_code}, URL: {r3.request.url}\n")

            # Complete sale
            response = client.post('/billing/complete', data={
                'discount_type': 'amount',
                'discount_value': '20.00',
                'payment_cash': '368.90'
            }, follow_redirects=True)

            f_log.write(f"COMPLETE STATUS: {response.status_code}\n")
            f_log.write(f"COMPLETE URL: {response.request.url}\n")
            f_log.write(f"COMPLETE FINAL DATA: {response.get_data(as_text=True)[:2000]}\n")

        # 5. Verify Database
        sale = Sale.query.order_by(Sale.id.desc()).first()
        assert sale is not None
        assert sale.total_amount == Decimal('340.00')
        assert sale.discount_amount == Decimal('60.00')
        assert sale.gst_total == Decimal('28.90')
        assert sale.grand_total == Decimal('368.90')

        print("Calculation and persistence integrity verified!")

if __name__ == "__main__":
    pytest.main([__file__])
