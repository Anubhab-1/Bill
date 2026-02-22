import os
import uuid
from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    with db.engine.connect() as conn:
        # Step 1: Add the column allowing NULLs
        try:
            conn.execute(text("ALTER TABLE products ADD COLUMN barcode VARCHAR(100)"))
            print("Added barcode column.")
        except Exception as e:
            print(f"Barcode column already exists or error: {e}")

        # Step 2: Update existing rows with a unique UUID barcode
        print("Updating existing rows with unique barcodes...")
        rows = conn.execute(text("SELECT id FROM products WHERE barcode IS NULL")).fetchall()
        for row in rows:
            unique_barcode = f"LEGACY-{uuid.uuid4().hex[:8].upper()}"
            conn.execute(
                text("UPDATE products SET barcode = :barcode WHERE id = :id"),
                {"barcode": unique_barcode, "id": row[0]}
            )

        # Step 3: Add NOT NULL constraint
        try:
            conn.execute(text("ALTER TABLE products ALTER COLUMN barcode SET NOT NULL"))
            print("Enforced NOT NULL constraint on barcode.")
        except Exception as e:
            print(f"Failed NOT NULL: {e}")

        # Step 4: Add UNIQUE constraint
        try:
            conn.execute(text("ALTER TABLE products ADD CONSTRAINT uq_products_barcode UNIQUE (barcode)"))
            print("Enforced UNIQUE constraint on barcode.")
        except Exception as e:
            print(f"Failed UNIQUE: {e}")

        conn.commit()
    print("Migration complete.")
