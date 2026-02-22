"""
Migration: Create product_batches table and seed LEGACY batches.
PostgreSQL-only migration.
Run: python add_batches_table.py
"""
import os
import sys

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text

os.environ['FLASK_RUN_FROM_CLI'] = '1'
sys.path.insert(0, os.getcwd())

from app import create_app, db

app = create_app()

with app.app_context():
    if db.engine.dialect.name != 'postgresql':
        raise RuntimeError('This migration requires PostgreSQL.')

    engine = db.engine
    inspector = sa_inspect(engine)

    with engine.connect() as conn:
        if 'product_batches' not in inspector.get_table_names():
            conn.execute(text("""
                CREATE TABLE product_batches (
                    id           SERIAL PRIMARY KEY,
                    product_id   INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                    batch_number VARCHAR(60) NOT NULL DEFAULT 'LEGACY',
                    expiry_date  DATE,
                    quantity     INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0),
                    cost_price   NUMERIC(10,2),
                    created_at   TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_pb_product_id ON product_batches(product_id)"))
            conn.commit()
            print("Table 'product_batches' created.")
        else:
            print("Table 'product_batches' already exists; skipping creation.")

        rows = conn.execute(text("""
            SELECT id, stock, price FROM products
            WHERE stock > 0
              AND id NOT IN (
                  SELECT product_id FROM product_batches WHERE batch_number = 'LEGACY'
              )
        """)).fetchall()

        for row in rows:
            conn.execute(text("""
                INSERT INTO product_batches (product_id, batch_number, quantity, cost_price)
                VALUES (:pid, 'LEGACY', :qty, :cost)
            """), {"pid": row.id, "qty": row.stock, "cost": row.price})

        conn.commit()
        print(f"Seeded {len(rows)} LEGACY batch(es) from existing stock.")
        print('Migration complete.')
