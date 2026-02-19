from app import create_app, db
from app.customers.models import Customer
import sys

app = create_app()

def test_search():
    with app.app_context():
        # 1. Create a purely test customer if not exists
        phone = "9999999999"
        cust = Customer.query.filter_by(phone=phone).first()
        if not cust:
            print(f"Creating test customer with phone {phone}")
            cust = Customer(name="Test Customer", phone=phone, email="test@example.com")
            db.session.add(cust)
            db.session.commit()
        else:
            print(f"Test customer found: {cust.name}")

        # 2. Test Partial Search (Name)
        print("\n--- Testing Name Search 'Test' ---")
        q = "Test"
        results = Customer.query.filter(
            (Customer.phone.ilike(f'%{q}%')) | 
            (Customer.name.ilike(f'%{q}%'))
        ).limit(10).all()
        print(f"Found {len(results)} results")
        for c in results:
            print(f" - {c.name} ({c.phone})")

        # 3. Test Partial Search (Phone)
        print("\n--- Testing Phone Search '99999' ---")
        q = "99999"
        results = Customer.query.filter(
            (Customer.phone.ilike(f'%{q}%')) | 
            (Customer.name.ilike(f'%{q}%'))
        ).limit(10).all()
        print(f"Found {len(results)} results")
        for c in results:
            print(f" - {c.name} ({c.phone})")

if __name__ == "__main__":
    try:
        test_search()
        print("\nBackend Logic: OK")
    except Exception as e:
        print(f"\nBackend Logic: FAILED - {e}")
