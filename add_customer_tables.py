
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from app import create_app, db
from app.customers.models import Customer, GiftCard
from sqlalchemy import text

def migrate():
    app = create_app()
    with app.app_context():
        # 1. Create new tables
        print("Creating 'customers' and 'gift_cards' tables...")
        db.create_all() # This creates only missing tables

        # 2. Add customer_id to sales table if not exists (SQLite limitation workaround)
        # SQLite doesn't support ADD COLUMN with ForeignKey easily in one go, 
        # but modern SQLite supports ADD COLUMN.
        
        with db.engine.connect() as conn:
            try:
                # Check if column exists
                result = conn.execute(text("PRAGMA table_info(sales)"))
                columns = [row[1] for row in result.fetchall()]
                
                if 'customer_id' not in columns:
                    print("Adding 'customer_id' column to 'sales' table...")
                    # We can use pure SQL for this
                    conn.execute(text("ALTER TABLE sales ADD COLUMN customer_id INTEGER REFERENCES customers(id)"))
                    conn.commit()
                    print("Column added successfully.")
                else:
                    print("'customer_id' column already exists in 'sales'.")
                    
            except Exception as e:
                print(f"Migration error: {e}")
                # If using Postgres, the ALTER TABLE syntax is fine too.
                # For safety in production, we'd use Alembic.

if __name__ == '__main__':
    migrate()
