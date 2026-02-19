from app import create_app, db
from app.billing.models import SalePayment
from sqlalchemy import text

app = create_app()

with app.app_context():
    print("Creating 'sale_payments' table...")
    try:
        # Check if table exists
        inspector = db.inspect(db.engine)
        if not inspector.has_table('sale_payments'):
            SalePayment.__table__.create(db.engine)
            print("Created 'sale_payments' table.")
        else:
            print("'sale_payments' table already exists.")
            
        print("Migration complete!")
        
    except Exception as e:
        print(f"Error during migration: {e}")
