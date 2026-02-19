"""
add_purchasing_tables.py
------------------------
Migration: Create the 5 purchasing tables.
Safe to re-run — skips any table that already exists.

Run: python add_purchasing_tables.py
"""
import os, sys
os.environ['FLASK_RUN_FROM_CLI'] = '1'
sys.path.insert(0, os.getcwd())

from app import create_app, db
from sqlalchemy import text, inspect as sa_inspect

app = create_app()

TABLES_DDL = [
    # ── suppliers ─────────────────────────────────────────────────
    (
        'suppliers',
        """
        CREATE TABLE suppliers (
            id         SERIAL PRIMARY KEY,
            name       VARCHAR(200) NOT NULL,
            contact    VARCHAR(200),
            gst_no     VARCHAR(20),
            address    TEXT,
            is_active  BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    ),
    (
        'suppliers',   # SQLite fallback DDL stored separately below
        """
        CREATE TABLE suppliers (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       VARCHAR(200) NOT NULL,
            contact    VARCHAR(200),
            gst_no     VARCHAR(20),
            address    TEXT,
            is_active  BOOLEAN NOT NULL DEFAULT 1,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    ),
    # ── purchase_orders ───────────────────────────────────────────
    (
        'purchase_orders',
        """
        CREATE TABLE purchase_orders (
            id            SERIAL PRIMARY KEY,
            supplier_id   INT NOT NULL REFERENCES suppliers(id),
            status        VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
            created_by    INT REFERENCES users(id),
            expected_date DATE,
            notes         TEXT,
            created_at    TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at    TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE purchase_orders (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id   INT NOT NULL REFERENCES suppliers(id),
            status        VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
            created_by    INT REFERENCES users(id),
            expected_date DATE,
            notes         TEXT,
            created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    ),
    # ── purchase_order_items ──────────────────────────────────────
    (
        'purchase_order_items',
        """
        CREATE TABLE purchase_order_items (
            id          SERIAL PRIMARY KEY,
            po_id       INT NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
            product_id  INT NOT NULL REFERENCES products(id),
            ordered_qty INT NOT NULL,
            unit_cost   NUMERIC(10,2)
        )
        """,
        """
        CREATE TABLE purchase_order_items (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            po_id       INT NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
            product_id  INT NOT NULL REFERENCES products(id),
            ordered_qty INT NOT NULL,
            unit_cost   NUMERIC(10,2)
        )
        """
    ),
    # ── goods_receipts ────────────────────────────────────────────
    (
        'goods_receipts',
        """
        CREATE TABLE goods_receipts (
            id            SERIAL PRIMARY KEY,
            po_id         INT NOT NULL REFERENCES purchase_orders(id),
            received_by   INT REFERENCES users(id),
            received_date DATE NOT NULL DEFAULT CURRENT_DATE,
            notes         TEXT,
            created_at    TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE goods_receipts (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            po_id         INT NOT NULL REFERENCES purchase_orders(id),
            received_by   INT REFERENCES users(id),
            received_date DATE NOT NULL DEFAULT CURRENT_DATE,
            notes         TEXT,
            created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    ),
    # ── goods_receipt_items ───────────────────────────────────────
    (
        'goods_receipt_items',
        """
        CREATE TABLE goods_receipt_items (
            id           SERIAL PRIMARY KEY,
            grn_id       INT NOT NULL REFERENCES goods_receipts(id) ON DELETE CASCADE,
            po_item_id   INT NOT NULL REFERENCES purchase_order_items(id),
            received_qty INT NOT NULL,
            batch_number VARCHAR(60),
            expiry_date  DATE
        )
        """,
        """
        CREATE TABLE goods_receipt_items (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            grn_id       INT NOT NULL REFERENCES goods_receipts(id) ON DELETE CASCADE,
            po_item_id   INT NOT NULL REFERENCES purchase_order_items(id),
            received_qty INT NOT NULL,
            batch_number VARCHAR(60),
            expiry_date  DATE
        )
        """
    ),
]

with app.app_context():
    inspector = sa_inspect(db.engine)
    is_pg     = db.engine.dialect.name == 'postgresql'
    existing  = set(inspector.get_table_names())

    with db.engine.connect() as conn:
        for entry in TABLES_DDL:
            table_name = entry[0]
            pg_ddl     = entry[1]
            sqlite_ddl = entry[2] if len(entry) > 2 else pg_ddl

            # Skip duplicates in our list (pg/sqlite entries share table_name)
            if table_name in existing:
                print(f'ℹ️   {table_name} already exists — skipping.')
                existing.discard(table_name)   # prevent "already exists" double-print
                continue

            ddl = pg_ddl if is_pg else sqlite_ddl
            try:
                conn.execute(text(ddl.strip()))
                conn.commit()
                existing.add(table_name)
                print(f'✅  Created {table_name}.')
            except Exception as e:
                conn.rollback()
                print(f'❌  Error creating {table_name}: {e}')

    print('✅  Purchasing tables migration complete.')
