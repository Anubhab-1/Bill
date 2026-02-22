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
            logger.info("[INFO] Checking database schema (Robust Mode)...")
            
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
            with db.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                try:
                    inspector = inspect(conn)

                    def column_exists(table_name, column_name):
                        try:
                            return any(c["name"] == column_name for c in inspector.get_columns(table_name))
                        except Exception:
                            return False

                    # Sales: payment_method
                    conn.execute(text("ALTER TABLE sales ADD COLUMN IF NOT EXISTS payment_method VARCHAR(20) DEFAULT 'cash' NOT NULL"))
                    # Sales: is_printed
                    conn.execute(text("ALTER TABLE sales ADD COLUMN IF NOT EXISTS is_printed BOOLEAN DEFAULT FALSE"))
                    # Sales: customer_id
                    conn.execute(text("ALTER TABLE sales ADD COLUMN IF NOT EXISTS customer_id INTEGER REFERENCES customers(id)"))
                    
                    # Sales: print_html (invoice snapshot)
                    conn.execute(text("ALTER TABLE sales ADD COLUMN IF NOT EXISTS print_html TEXT"))
                    # Sales: discount snapshot fields
                    conn.execute(text("ALTER TABLE sales ADD COLUMN IF NOT EXISTS discount_percent NUMERIC(5,2) DEFAULT 0 NOT NULL"))
                    conn.execute(text("ALTER TABLE sales ADD COLUMN IF NOT EXISTS discount_amount NUMERIC(12,2) DEFAULT 0 NOT NULL"))
                    
                    # Products: is_active
                    conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE NOT NULL"))
                    # Products: is_weighed
                    conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS is_weighed BOOLEAN DEFAULT FALSE NOT NULL"))
                    # Products: apparel metadata
                    conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS brand VARCHAR(100)"))
                    conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS category VARCHAR(100)"))
                    conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS description TEXT"))
                    # Products: price_per_kg
                    conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS price_per_kg NUMERIC(10,2)"))
                    
                    # Users: is_active
                    conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE NOT NULL"))
                    
                    # Customers: is_active
                    conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE NOT NULL"))
                    
                    # SaleItems: weight_kg
                    conn.execute(text("ALTER TABLE sale_items ADD COLUMN IF NOT EXISTS weight_kg NUMERIC(8,3)"))
                    # SaleItems: unit_label
                    conn.execute(text("ALTER TABLE sale_items ADD COLUMN IF NOT EXISTS unit_label VARCHAR(10)"))
                    # SaleItems: variant snapshots
                    conn.execute(text("ALTER TABLE sale_items ADD COLUMN IF NOT EXISTS variant_id INTEGER REFERENCES product_variants(id)"))
                    conn.execute(text("ALTER TABLE sale_items ADD COLUMN IF NOT EXISTS snapshot_size VARCHAR(10)"))
                    conn.execute(text("ALTER TABLE sale_items ADD COLUMN IF NOT EXISTS snapshot_color VARCHAR(50)"))

                    # Fallbacks for partially migrated PostgreSQL schemas.
                    if not column_exists('products', 'brand'):
                        conn.execute(text("ALTER TABLE products ADD COLUMN brand VARCHAR(100)"))
                    if not column_exists('products', 'category'):
                        conn.execute(text("ALTER TABLE products ADD COLUMN category VARCHAR(100)"))
                    if not column_exists('products', 'description'):
                        conn.execute(text("ALTER TABLE products ADD COLUMN description TEXT"))
                    if not column_exists('sales', 'print_html'):
                        conn.execute(text("ALTER TABLE sales ADD COLUMN print_html TEXT"))
                    if not column_exists('sales', 'discount_percent'):
                        conn.execute(text("ALTER TABLE sales ADD COLUMN discount_percent NUMERIC(5,2) DEFAULT 0 NOT NULL"))
                    if not column_exists('sales', 'discount_amount'):
                        conn.execute(text("ALTER TABLE sales ADD COLUMN discount_amount NUMERIC(12,2) DEFAULT 0 NOT NULL"))

                    if not column_exists('sale_items', 'variant_id'):
                        conn.execute(text("ALTER TABLE sale_items ADD COLUMN variant_id INTEGER REFERENCES product_variants(id)"))
                    if not column_exists('sale_items', 'snapshot_size'):
                        conn.execute(text("ALTER TABLE sale_items ADD COLUMN snapshot_size VARCHAR(10)"))
                    if not column_exists('sale_items', 'snapshot_color'):
                        conn.execute(text("ALTER TABLE sale_items ADD COLUMN snapshot_color VARCHAR(50)"))

                    if not column_exists('users', 'is_active'):
                        conn.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT TRUE NOT NULL"))
                    if not column_exists('customers', 'is_active'):
                        conn.execute(text("ALTER TABLE customers ADD COLUMN is_active BOOLEAN DEFAULT TRUE NOT NULL"))

                    # InventoryLog: reference (PO/GRN etc.)
                    conn.execute(text("ALTER TABLE inventory_logs ADD COLUMN IF NOT EXISTS reference INTEGER"))
                    # Performance indexes for reporting queries
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_product_variants_barcode ON product_variants (barcode)"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_sale_items_variant_id ON sale_items (variant_id)"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_sales_created_at ON sales (created_at)"))

                    # Legacy data cleanup:
                    # 1) Create a default variant for products that still only have legacy product-level stock/price/barcode.
                    # 2) Backfill sale_items.variant_id and snapshot fields from product_id/default variant.
                    conn.execute(text("""
                        INSERT INTO product_variants (product_id, size, color, sku, barcode, price, stock, is_active, created_at)
                        SELECT
                            p.id,
                            'STD',
                            'Default',
                            NULL,
                            CASE
                                WHEN p.barcode IS NULL OR p.barcode = '' THEN ('LEGACY-' || p.id::text)
                                ELSE p.barcode
                            END,
                            CASE
                                WHEN p.price IS NULL OR p.price <= 0 THEN 1
                                ELSE p.price
                            END,
                            CASE
                                WHEN p.stock IS NULL OR p.stock < 0 THEN 0
                                ELSE p.stock
                            END,
                            TRUE,
                            NOW()
                        FROM products p
                        LEFT JOIN product_variants pv
                            ON pv.product_id = p.id AND pv.is_active = TRUE
                        WHERE pv.id IS NULL
                        ON CONFLICT (barcode) DO NOTHING
                    """))
                    conn.execute(text("""
                        INSERT INTO product_variants (product_id, size, color, sku, barcode, price, stock, is_active, created_at)
                        SELECT
                            p.id,
                            'STD',
                            'Default',
                            NULL,
                            ('LEGACY-' || lpad(p.id::text, 10, '0')),
                            CASE
                                WHEN p.price IS NULL OR p.price <= 0 THEN 1
                                ELSE p.price
                            END,
                            CASE
                                WHEN p.stock IS NULL OR p.stock < 0 THEN 0
                                ELSE p.stock
                            END,
                            TRUE,
                            NOW()
                        FROM products p
                        LEFT JOIN product_variants pv
                            ON pv.product_id = p.id AND pv.is_active = TRUE
                        WHERE pv.id IS NULL
                        ON CONFLICT (barcode) DO NOTHING
                    """))
                    conn.execute(text("""
                        WITH default_variant AS (
                            SELECT product_id, MIN(id) AS variant_id
                            FROM product_variants
                            GROUP BY product_id
                        )
                        UPDATE sale_items si
                        SET variant_id = dv.variant_id
                        FROM default_variant dv
                        WHERE si.variant_id IS NULL
                          AND si.product_id = dv.product_id
                    """))
                    conn.execute(text("""
                        UPDATE sale_items si
                        SET snapshot_size = COALESCE(si.snapshot_size, pv.size),
                            snapshot_color = COALESCE(si.snapshot_color, pv.color)
                        FROM product_variants pv
                        WHERE si.variant_id = pv.id
                          AND (si.snapshot_size IS NULL OR si.snapshot_color IS NULL)
                    """))

                    constraints = [
                        ("check_variant_stock_non_negative", "ALTER TABLE product_variants ADD CONSTRAINT check_variant_stock_non_negative CHECK (stock >= 0)"),
                        ("check_variant_price_positive", "ALTER TABLE product_variants ADD CONSTRAINT check_variant_price_positive CHECK (price > 0)"),
                        ("check_sale_totals_non_negative", "ALTER TABLE sales ADD CONSTRAINT check_sale_totals_non_negative CHECK (total_amount >= 0 AND gst_total >= 0 AND discount_amount >= 0)"),
                        ("check_sale_discount_percent_valid", "ALTER TABLE sales ADD CONSTRAINT check_sale_discount_percent_valid CHECK (discount_percent >= 0 AND discount_percent <= 100)"),
                        ("check_sale_item_qty_positive", "ALTER TABLE sale_items ADD CONSTRAINT check_sale_item_qty_positive CHECK (quantity > 0)"),
                        ("check_sale_item_subtotal_non_negative", "ALTER TABLE sale_items ADD CONSTRAINT check_sale_item_subtotal_non_negative CHECK (subtotal >= 0)"),
                        ("check_sale_payment_amount_non_negative", "ALTER TABLE sale_payments ADD CONSTRAINT check_sale_payment_amount_non_negative CHECK (amount >= 0)"),
                        ("check_return_total_non_negative", "ALTER TABLE returns ADD CONSTRAINT check_return_total_non_negative CHECK (total_refunded >= 0)"),
                        ("check_return_item_qty_positive", "ALTER TABLE return_items ADD CONSTRAINT check_return_item_qty_positive CHECK (quantity > 0)"),
                        ("check_return_item_refund_non_negative", "ALTER TABLE return_items ADD CONSTRAINT check_return_item_refund_non_negative CHECK (refund_amount >= 0)"),
                        ("check_cash_session_amounts_non_negative", "ALTER TABLE cash_sessions ADD CONSTRAINT check_cash_session_amounts_non_negative CHECK (opening_cash >= 0 AND system_total >= 0 AND (closing_cash IS NULL OR closing_cash >= 0))"),
                        ("check_customer_points_non_negative", "ALTER TABLE customers ADD CONSTRAINT check_customer_points_non_negative CHECK (points >= 0)"),
                        ("check_gift_card_balances_non_negative", "ALTER TABLE gift_cards ADD CONSTRAINT check_gift_card_balances_non_negative CHECK (initial_balance >= 0 AND balance >= 0)"),
                        ("check_gift_card_balance_within_initial", "ALTER TABLE gift_cards ADD CONSTRAINT check_gift_card_balance_within_initial CHECK (balance <= initial_balance)"),
                        ("check_po_item_qty_positive", "ALTER TABLE purchase_order_items ADD CONSTRAINT check_po_item_qty_positive CHECK (ordered_qty > 0)"),
                        ("check_po_item_unit_cost_non_negative", "ALTER TABLE purchase_order_items ADD CONSTRAINT check_po_item_unit_cost_non_negative CHECK (unit_cost IS NULL OR unit_cost >= 0)"),
                        ("check_grn_item_qty_positive", "ALTER TABLE goods_receipt_items ADD CONSTRAINT check_grn_item_qty_positive CHECK (received_qty > 0)"),
                    ]
                    for _name, sql in constraints:
                        try:
                            # Using savepoints so a single constraint failure doesn't crash the script
                            # Wait, AUTOCOMMIT ignores savepoints, but the query just fails and execution continues
                            conn.execute(text(sql))
                        except Exception as e:
                            logger.warning(f"Constraint skip: {e}")

                    logger.info("[OK] Database schema patched successfully.")

                except Exception as e:
                    logger.error(f"[WARN] SQL Patch warning: {e}")

        except Exception as e:
            logger.error(f"[ERROR] Migration wrapper failed: {e}")
