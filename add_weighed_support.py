"""
Migration: Add is_weighed / price_per_kg to products table
         and weight_kg / unit_label to sale_items table.
Run: python add_weighed_support.py
"""
import os, sys
os.environ['FLASK_RUN_FROM_CLI'] = '1'
sys.path.insert(0, os.getcwd())

from app import create_app, db
from sqlalchemy import text, inspect as sa_inspect

app = create_app()

with app.app_context():
    inspector = sa_inspect(db.engine)
    is_pg = db.engine.dialect.name == 'postgresql'

    with db.engine.connect() as conn:

        # ── products: is_weighed, price_per_kg ───────────────────────
        existing_prod_cols = [c['name'] for c in inspector.get_columns('products')]

        if 'is_weighed' not in existing_prod_cols:
            conn.execute(text(
                "ALTER TABLE products ADD COLUMN is_weighed BOOLEAN NOT NULL DEFAULT FALSE"
            ))
            print("✅  Added is_weighed to products.")
        else:
            print("ℹ️   is_weighed already exists.")

        if 'price_per_kg' not in existing_prod_cols:
            conn.execute(text(
                "ALTER TABLE products ADD COLUMN price_per_kg NUMERIC(10,2)"
            ))
            print("✅  Added price_per_kg to products.")
        else:
            print("ℹ️   price_per_kg already exists.")

        # ── sale_items: weight_kg, unit_label ────────────────────────
        existing_si_cols = [c['name'] for c in inspector.get_columns('sale_items')]

        if 'weight_kg' not in existing_si_cols:
            conn.execute(text(
                "ALTER TABLE sale_items ADD COLUMN weight_kg NUMERIC(8,3)"
            ))
            print("✅  Added weight_kg to sale_items.")
        else:
            print("ℹ️   weight_kg already exists.")

        if 'unit_label' not in existing_si_cols:
            conn.execute(text(
                "ALTER TABLE sale_items ADD COLUMN unit_label VARCHAR(10)"
            ))
            print("✅  Added unit_label to sale_items.")
        else:
            print("ℹ️   unit_label already exists.")

        conn.commit()
        print("✅  Migration complete.")
