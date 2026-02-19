from app import create_app, db
from sqlalchemy import text
import os

app = create_app(os.environ.get('FLASK_ENV', 'production'))

with app.app_context():
    try:
        with db.engine.connect() as conn:
            # Check if column exists, then add. Or just try adding (IF NOT EXISTS only works in recent PG versions for add column?)
            # PG 9.6+ supports IF NOT EXISTS on ADD COLUMN.
            conn.execute(text("ALTER TABLE sales ADD COLUMN print_html TEXT"))
            conn.commit()
        print("✅ Column 'print_html' added successfully.")
    except Exception as e:
        print(f"❌ Error adding column: {e}")
