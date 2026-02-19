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
            logger.info("🔄 Checking database schema...")
            
            # 0. Compare imports to ensure all models are known to SQLAlchemy
            # (Importing them registers them with db.metadata)
            import app.auth.models
            import app.inventory.models
            import app.billing.models
            import app.promotions.models
            import app.customers.models
            import app.purchasing.models
            
            # 1. Create missing tables
            db.create_all()
            
            # 2. Add columns to existing tables using Inspector
            with db.engine.connect() as conn:
                inspector = inspect(conn)
                
                # Check for table existence first
                existing_tables = inspector.get_tables()

                def column_exists(table, column):
                    if table not in existing_tables:
                        return False
                    cols = [c['name'] for c in inspector.get_columns(table)]
                    return column in cols

                # --- MIGRATIONS ---

                # Sales: payment_method
                if 'sales' in existing_tables and not column_exists('sales', 'payment_method'):
                    logger.info("🛠️  Adding 'payment_method' to sales")
                    conn.execute(text("ALTER TABLE sales ADD COLUMN payment_method VARCHAR(20) DEFAULT 'cash' NOT NULL"))

                # Sales: is_printed
                if 'sales' in existing_tables and not column_exists('sales', 'is_printed'):
                    logger.info("🛠️  Adding 'is_printed' to sales")
                    conn.execute(text("ALTER TABLE sales ADD COLUMN is_printed BOOLEAN DEFAULT FALSE"))

                # Sales: customer_id
                if 'customers' in existing_tables and 'sales' in existing_tables and not column_exists('sales', 'customer_id'):
                    logger.info("🛠️  Adding 'customer_id' to sales")
                    conn.execute(text("ALTER TABLE sales ADD COLUMN customer_id INTEGER REFERENCES customers(id)"))

                # Products: is_active
                if 'products' in existing_tables and not column_exists('products', 'is_active'):
                    logger.info("🛠️  Adding 'is_active' to products")
                    conn.execute(text("ALTER TABLE products ADD COLUMN is_active BOOLEAN DEFAULT TRUE NOT NULL"))

                # Products: is_weighed (THE CRITICAL FIX)
                if 'products' in existing_tables and not column_exists('products', 'is_weighed'):
                    logger.info("🛠️  Adding 'is_weighed' to products")
                    conn.execute(text("ALTER TABLE products ADD COLUMN is_weighed BOOLEAN DEFAULT FALSE NOT NULL"))

                # Products: price_per_kg
                if 'products' in existing_tables and not column_exists('products', 'price_per_kg'):
                    logger.info("🛠️  Adding 'price_per_kg' to products")
                    conn.execute(text("ALTER TABLE products ADD COLUMN price_per_kg NUMERIC(10,2)"))

                # SaleItems: weight_kg
                if 'sale_items' in existing_tables and not column_exists('sale_items', 'weight_kg'):
                    logger.info("🛠️  Adding 'weight_kg' to sale_items")
                    conn.execute(text("ALTER TABLE sale_items ADD COLUMN weight_kg NUMERIC(8,3)"))

                # SaleItems: unit_label
                if 'sale_items' in existing_tables and not column_exists('sale_items', 'unit_label'):
                    logger.info("🛠️  Adding 'unit_label' to sale_items")
                    conn.execute(text("ALTER TABLE sale_items ADD COLUMN unit_label VARCHAR(10)"))

                conn.commit()
                logger.info("✅ Database schema check complete.")

        except Exception as e:
            logger.error(f"❌ Schema migration failed: {e}")
            # We don't raise here to allow app to try starting, 
            # but ideally this should be fixed.
