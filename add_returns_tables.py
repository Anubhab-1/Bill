from app import create_app, db
from app.billing.models import Return, ReturnItem
from sqlalchemy import text

app = create_app()

with app.app_context():
    print("Creating 'returns' and 'return_items' tables...")
    try:
        # Check if tables exist
        inspector = db.inspect(db.engine)
        if not inspector.has_table('returns'):
            Return.__table__.create(db.engine)
            print("Created 'returns' table.")
        else:
            print("'returns' table already exists.")

        if not inspector.has_table('return_items'):
            ReturnItem.__table__.create(db.engine)
            print("Created 'return_items' table.")
        else:
            print("'return_items' table already exists.")
            
        print("Migration complete!")
        
    except Exception as e:
        print(f"Error during migration: {e}")
