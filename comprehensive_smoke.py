import unittest
import urllib.request
import urllib.error
import urllib.parse
from app import create_app, db
from app.auth.models import User, RoleEnum
from app.billing.models import CashSession
from app.inventory.models import Product
from decimal import Decimal

# Setup a test app context
app = create_app()

class ComprehensiveSmokeTest(unittest.TestCase):
    BASE_URL = "http://127.0.0.1:5000"

    def setUp(self):
        self.app_context = app.app_context()
        self.app_context.push()
        self.client = app.test_client()
        
        # Create/Get test admin user
        self.username = 'test_admin'
        self.password = 'testpass'
        
        self.admin = User.query.filter_by(username=self.username).first()
        if not self.admin:
            self.admin = User(
                name='Test Admin',
                username=self.username,
                role=RoleEnum.admin
            )
            self.admin.set_password(self.password)
            db.session.add(self.admin)
            db.session.commit()
        else:
            # Ensure password is correct
            self.admin.set_password(self.password)
            db.session.commit()

    def tearDown(self):
        # Optional: remove test user? No, keep it for debugging
        self.app_context.pop()

    def login(self):
        return self.client.post('/auth/login', data=dict(
            username=self.username,
            password=self.password 
        ), follow_redirects=True)

    def test_01_public_routes(self):
        """Check public routes (login)"""
        print("\n[TEST] Public Routes...")
        response = self.client.get('/auth/login')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Sign in', response.data)
        print(" -> Login Page OK")

    def test_02_admin_login_access(self):
        """Check dashboard access after login"""
        print("\n[TEST] Admin Access...")
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Dashboard', response.data)
        print(" -> Login OK")

        # Dashboard Stats check
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Today's Revenue", response.data)
        print(" -> Dashboard OK")

    def test_03_inventory_routes(self):
        """Check inventory pages"""
        print("\n[TEST] Inventory...")
        self.login()
        response = self.client.get('/inventory/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Inventory', response.data)
        print(" -> Inventory List OK")

        response = self.client.get('/inventory/new')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Barcode', response.data)
        print(" -> New Product Form OK")

    def test_04_billing_routes(self):
        """Check billing pages"""
        print("\n[TEST] Billing...")
        self.login()
        
        # Ensure session exists
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.admin.id

        # Bypass session check by mocking or ensuring a session exists
        # Actually, let's just hit the route and see if it redirects to open_session
        response = self.client.get('/billing/')
        if response.status_code == 302 and '/billing/session/open' in response.location:
             print(" -> Redirects to Open Session (Expected if no session)")
        else:
             self.assertEqual(response.status_code, 200)
             print(" -> Billing Page OK")

    def test_05_reports_routes(self):
         """Check report pages"""
         print("\n[TEST] Reports...")
         self.login()
         routes = [
             '/reports/',              # Sales List
             '/reporting/',            # Dashboard
             '/reporting/sales',       # Sales Analytics
             '/reporting/gst',         # GST Report
             '/reporting/inventory'    # Inventory Report
         ]
         for route in routes:
             try:
                 response = self.client.get(route)
                 if response.status_code != 200:
                     print(f"\n[ERROR] Route {route} failed with {response.status_code}")
                     # Print visible error from response
                     print(f"Response snippet: {response.get_data(as_text=True)[:500]}")
                 self.assertEqual(response.status_code, 200, f"Failed on {route}")
                 print(f" -> {route} OK")
             except Exception as e:
                 print(f"\n[CRITICAL] Exception accessing {route}: {e}")
                 import traceback
                 traceback.print_exc()
                 raise e

    def test_06_promotions_routes(self):
         """Check promotion pages"""
         print("\n[TEST] Promotions...")
         self.login()
         response = self.client.get('/promotions/')
         self.assertEqual(response.status_code, 200)
         print(" -> Promotions List OK")

if __name__ == '__main__':
    unittest.main()
