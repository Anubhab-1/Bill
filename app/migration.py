import logging
from sqlalchemy import text, inspect
from app import db

logger = logging.getLogger(__name__)

def run_auto_migration(app):
    """
    Automatically adds missing columns/tables on startup.
    This replaces the need for external 'flask patch-db' commands.
    """
    with app.app_context():
        try:
            logger.info("🔄 Checking database schema (Robust Mode)...")
            
            # 0. Ensure models allowed
            import app.auth.models
            import app.inventory.models
            import app.billing.models
            import app.promotions.models
            import app.customers.models
            import app.purchasing.models
            
            # 1. Create missing tables
            db.create_all()
            
            # 2. Add columns using PostgreSQL 'IF NOT EXISTS' 
            # This is safer and doesn't rely on Inspector
            with db.engine.connect() as conn:
                try:
                    # Sales: payment_method
                    conn.execute(text("ALTER TABLE sales ADD COLUMN IF NOT EXISTS payment_method VARCHAR(20) DEFAULT 'cash' NOT NULL"))
                    # Sales: is_printed
                    conn.execute(text("ALTER TABLE sales ADD COLUMN IF NOT EXISTS is_printed BOOLEAN DEFAULT FALSE"))
                    # Sales: customer_id
                    conn.execute(text("ALTER TABLE sales ADD COLUMN IF NOT EXISTS customer_id INTEGER REFERENCES customers(id)"))
                    
                    # Sales: print_html (invoice snapshot)
                    conn.execute(text("ALTER TABLE sales ADD COLUMN IF NOT EXISTS print_html TEXT"))
                    
                    # Products: is_active
                    conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE NOT NULL"))
                    # Products: is_weighed
                    conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS is_weighed BOOLEAN DEFAULT FALSE NOT NULL"))
                    # Products: price_per_kg
                    conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS price_per_kg NUMERIC(10,2)"))
                    
                    # SaleItems: weight_kg
                    conn.execute(text("ALTER TABLE sale_items ADD COLUMN IF NOT EXISTS weight_kg NUMERIC(8,3)"))
                    # SaleItems: unit_label
                    conn.execute(text("ALTER TABLE sale_items ADD COLUMN IF NOT EXISTS unit_label VARCHAR(10)"))

                    conn.commit()
                    logger.info("✅ Database schema patched successfully.")
                except Exception as e:
                    logger.error(f"⚠️ SQL Patch warning: {e}")

        except Exception as e:
            logger.error(f"❌ Migration wrapper failed: {e}")
