"""
Ensure unique key safety for invoice_sequences(year).

PostgreSQL:
- validate no duplicate year rows
- create unique index concurrently only if uniqueness is missing

Run:
    python add_invoice_sequence_unique_index.py
"""
import os
import sys

from sqlalchemy import text

os.environ['FLASK_RUN_FROM_CLI'] = '1'
sys.path.insert(0, os.getcwd())

from app import create_app, db  # noqa: E402


INDEX_NAME = 'uq_invoice_sequences_year'


def ensure_invoice_sequence_unique_year(app=None):
    app = app or create_app(os.environ.get('FLASK_ENV', 'development'))

    with app.app_context():
        if db.engine.dialect.name != 'postgresql':
            raise RuntimeError('This migration requires PostgreSQL.')

        with db.engine.connect() as conn:
            dup_count = conn.execute(text("""
                SELECT COUNT(*) FROM (
                    SELECT year
                    FROM invoice_sequences
                    GROUP BY year
                    HAVING COUNT(*) > 1
                ) d
            """)).scalar() or 0
        if dup_count > 0:
            raise RuntimeError(
                f'Cannot enforce uniqueness: found {dup_count} duplicate year rows '
                'in invoice_sequences.'
            )

        with db.engine.connect() as conn:
            has_unique = conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1
                    FROM pg_indexes
                    WHERE schemaname = current_schema()
                      AND tablename = 'invoice_sequences'
                      AND indexdef ILIKE 'CREATE UNIQUE INDEX%'
                      AND indexdef ILIKE '%(year)%'
                )
            """))
            has_unique = bool(has_unique.scalar())
        if has_unique:
            return 'already_unique_postgresql'

        with db.engine.connect().execution_options(isolation_level='AUTOCOMMIT') as conn:
            conn.execute(text(f"""
                CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME}
                ON invoice_sequences (year)
            """))
        return 'created_postgresql'


if __name__ == '__main__':
    print(ensure_invoice_sequence_unique_year())
