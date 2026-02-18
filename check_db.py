from app import create_app, db
from sqlalchemy import text

app = create_app('development')
with app.app_context():
    try:
        with db.engine.connect() as conn:
            conn.execute(text("SELECT is_active FROM products LIMIT 1"))
        print("\n✅ is_active column exists.")
    except Exception as e:
        print(f"\n❌ is_active column missing or error: {e}")
