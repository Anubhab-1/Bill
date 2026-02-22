"""
Pre-migration cleanup for product batch duplicates.

Merges duplicate rows by (product_id, batch_number):
- keeps the oldest row (lowest id)
- sums quantity into keeper
- preserves first non-null expiry/cost when keeper is null
- deletes extra rows

Run:
    python cleanup_product_batch_duplicates.py
"""
import os
import sys

from sqlalchemy import text

os.environ['FLASK_RUN_FROM_CLI'] = '1'
sys.path.insert(0, os.getcwd())

from app import create_app, db  # noqa: E402


def cleanup_duplicate_product_batches(app=None):
    """Merge duplicate product_batches rows safely inside a single transaction."""
    app = app or create_app(os.environ.get('FLASK_ENV', 'development'))

    with app.app_context():
        merged_groups = 0
        deleted_rows = 0

        with db.engine.connect() as conn:
            duplicates = conn.execute(text("""
                SELECT product_id, batch_number, COUNT(*) AS cnt
                FROM product_batches
                GROUP BY product_id, batch_number
                HAVING COUNT(*) > 1
            """)).fetchall()

            for dup in duplicates:
                rows = conn.execute(text("""
                    SELECT id, quantity, expiry_date, cost_price
                    FROM product_batches
                    WHERE product_id = :pid AND batch_number = :batch
                    ORDER BY id ASC
                """), {'pid': dup.product_id, 'batch': dup.batch_number}).fetchall()
                if len(rows) <= 1:
                    continue

                keeper = rows[0]
                extras = rows[1:]

                total_qty = sum(r.quantity for r in rows)
                expiry_value = keeper.expiry_date
                if expiry_value is None:
                    for r in rows:
                        if r.expiry_date is not None:
                            expiry_value = r.expiry_date
                            break

                cost_value = keeper.cost_price
                if cost_value is None:
                    for r in rows:
                        if r.cost_price is not None:
                            cost_value = r.cost_price
                            break

                conn.execute(text("""
                    UPDATE product_batches
                    SET quantity = :qty,
                        expiry_date = :expiry,
                        cost_price = :cost
                    WHERE id = :id
                """), {
                    'qty': total_qty,
                    'expiry': expiry_value,
                    'cost': cost_value,
                    'id': keeper.id,
                })

                for row in extras:
                    conn.execute(
                        text("DELETE FROM product_batches WHERE id = :id"),
                        {'id': row.id},
                    )
                    deleted_rows += 1

                merged_groups += 1

            conn.commit()

        return {'merged_groups': merged_groups, 'deleted_rows': deleted_rows}


if __name__ == '__main__':
    stats = cleanup_duplicate_product_batches()
    print(
        f"Cleanup complete. merged_groups={stats['merged_groups']} "
        f"deleted_rows={stats['deleted_rows']}"
    )
