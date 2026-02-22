"""
Migration: add unique index on product_batches(product_id, batch_number).

PostgreSQL:
- validates no duplicates remain
- creates index concurrently (non-blocking write-safe approach)

Run:
    python add_product_batch_unique_index.py
"""
import os
import sys

from sqlalchemy import text

os.environ['FLASK_RUN_FROM_CLI'] = '1'
sys.path.insert(0, os.getcwd())

from app import create_app, db  # noqa: E402


INDEX_NAME = 'uq_product_batches_product_batch'


def add_product_batch_unique_index(app=None):
    app = app or create_app(os.environ.get('FLASK_ENV', 'development'))

    with app.app_context():
        if db.engine.dialect.name != 'postgresql':
            raise RuntimeError('This migration requires PostgreSQL.')

        with db.engine.connect() as conn:
            duplicate_count = conn.execute(text("""
                SELECT COUNT(*) FROM (
                    SELECT 1
                    FROM product_batches
                    GROUP BY product_id, batch_number
                    HAVING COUNT(*) > 1
                ) dup
            """)).scalar() or 0

        if duplicate_count > 0:
            raise RuntimeError(
                f'Cannot add unique index: found {duplicate_count} duplicate batch key groups. '
                'Run cleanup_product_batch_duplicates.py first.'
            )

        with db.engine.connect().execution_options(isolation_level='AUTOCOMMIT') as conn:
            conn.execute(text(f"""
                CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME}
                ON product_batches (product_id, batch_number)
            """))
        return 'created_postgresql'


if __name__ == '__main__':
    result = add_product_batch_unique_index()
    print(f'Unique index migration complete: {result}.')
