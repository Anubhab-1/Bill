import os
import sys

# Ensure we can import from app
sys.path.append(os.getcwd())

from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    try:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE sales ADD COLUMN is_printed BOOLEAN DEFAULT FALSE"))
            conn.commit()
            print("Successfully added 'is_printed' column to 'sales' table.")
    except Exception as e:
        print(f"Error (might already exist): {e}")
