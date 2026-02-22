from app import create_app, db
from sqlalchemy import text
from decimal import Decimal

def audit_phase3():
    app = create_app('development')
    print("PHASE 3 — DATABASE INTEGRITY VALIDATION\n")
    
    with app.app_context():
        checks = [
            ("1. Negative Stock (Variants)", "SELECT id, product_id, size, color, stock FROM product_variants WHERE stock < 0"),
            ("2. Duplicate Invoices", "SELECT invoice_number, COUNT(*) FROM sales GROUP BY invoice_number HAVING COUNT(*) > 1"),
            ("3. Sale Items referencing Invalid Sale", "SELECT id FROM sale_items WHERE sale_id NOT IN (SELECT id FROM sales)"),
            ("4. Return Items referencing Invalid Sale Item", "SELECT id FROM return_items WHERE sale_item_id NOT IN (SELECT id FROM sale_items)"),
            ("5. NULLs in Required Financial Columns (Sales)", "SELECT id FROM sales WHERE total_amount IS NULL OR gst_total IS NULL OR grand_total IS NULL"),
            ("6. NULLs in Required Financial Columns (Sale Items)", "SELECT id FROM sale_items WHERE price_at_sale IS NULL OR subtotal IS NULL OR quantity IS NULL"),
            ("7. Constraint Mismatch: GST Percent range (0-28)", "SELECT id, name FROM products WHERE gst_percent < 0 OR gst_percent > 28")
        ]
        
        for title, query in checks:
            print(f"Checking: {title}...")
            result = db.session.execute(text(query)).all()
            if result:
                print(f"  [CORRUPTION DETECTED] Found {len(result)} records:")
                for row in result[:5]:
                    print(f"    {row}")
                if len(result) > 5:
                    print("    ...")
            else:
                print("  OK.")
        
        # 8. Invoice Sequence Consistency
        print("Checking: 8. Invoice Sequence Consistency...")
        try:
            from datetime import datetime
            year = datetime.now().year
            seq_row = db.session.execute(text(f"SELECT last_seq FROM invoice_sequences WHERE year = {year}")).first()
            max_sale_row = db.session.execute(text("SELECT MAX(SUBSTRING(invoice_number FROM '[0-9]+$'))::INTEGER FROM sales")).first()
            
            last_seq = seq_row[0] if seq_row else 0
            max_sale_seq = max_sale_row[0] if max_sale_row and max_sale_row[0] else 0
            
            if last_seq < max_sale_seq:
                print(f"  [CONSISTENCY ERROR] InvoiceSequence.last_seq ({last_seq}) is less than Max Invoice Sequence in sales ({max_sale_seq})")
            else:
                print(f"  OK. (last_seq={last_seq}, max_sale_seq={max_sale_seq})")
        except Exception as e:
            print(f"  [ERROR] Inconsistency check failed: {e}")

if __name__ == "__main__":
    audit_phase3()
