"""
Migration: Create product_batches table and seed LEGACY batches.
Works with both SQLite (local dev) and PostgreSQL (production).
Run: python add_batches_table.py
"""
import os, sys, re
os.environ['FLASK_RUN_FROM_CLI'] = '1'   # Prevents module-level auto-init in app/__init__.py

sys.path.insert(0, os.getcwd())

from app import create_app, db
from sqlalchemy import text, inspect as sa_inspect

app = create_app()

with app.app_context():
    engine = db.engine
    inspector = sa_inspect(engine)
    is_pg = engine.dialect.name == 'postgresql'

    with engine.connect() as conn:
        # ── 1. Create table ──────────────────────────────────────────
        if 'product_batches' not in inspector.get_table_names():
            if is_pg:
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
                conn.execute(text("CREATE INDEX ix_pb_product_id ON product_batches(product_id)"))
            else:
                conn.execute(text("""
                    CREATE TABLE product_batches (
                        id           INTEGER PRIMARY KEY AUTOINCREMENT,
                        product_id   INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                        batch_number VARCHAR(60) NOT NULL DEFAULT 'LEGACY',
                        expiry_date  DATE,
                        quantity     INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0),
                        cost_price   NUMERIC(10,2),
                        created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_pb_product_id ON product_batches(product_id)"))
            conn.commit()
            print("✅  Table 'product_batches' created.")
        else:
            print("ℹ️   Table 'product_batches' already exists — skipping creation.")

        # ── 2. Seed LEGACY batches ────────────────────────────────────
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
        print(f"✅  Seeded {len(rows)} LEGACY batch(es) from existing stock.")
        print("✅  Migration complete.")
