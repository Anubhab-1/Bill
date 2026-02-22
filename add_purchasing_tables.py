"""
add_purchasing_tables.py
------------------------
Migration: Create the 5 purchasing tables.
Safe to re-run on PostgreSQL.

Run: python add_purchasing_tables.py
"""
import os
import sys

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text

os.environ['FLASK_RUN_FROM_CLI'] = '1'
sys.path.insert(0, os.getcwd())

from app import create_app, db

app = create_app()

TABLES_DDL = [
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
        """,
    ),
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
    ),
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
    ),
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
    ),
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
    ),
]

with app.app_context():
    if db.engine.dialect.name != 'postgresql':
        raise RuntimeError('This migration requires PostgreSQL.')

    inspector = sa_inspect(db.engine)
    existing = set(inspector.get_table_names())

    with db.engine.connect() as conn:
        for table_name, ddl in TABLES_DDL:
            if table_name in existing:
                print(f'{table_name} already exists; skipping.')
                continue
            try:
                conn.execute(text(ddl.strip()))
                conn.commit()
                print(f'Created {table_name}.')
            except Exception as e:
                conn.rollback()
                print(f'Error creating {table_name}: {e}')

    print('Purchasing tables migration complete.')
