"""
Migration: add nullable `reference` column to inventory_logs.
Used for linking inventory mutations to source records (e.g., PO id).

Run:
    python add_inventory_log_reference_column.py
"""
import os
import sys

from sqlalchemy import text

os.environ['FLASK_RUN_FROM_CLI'] = '1'
sys.path.insert(0, os.getcwd())

from app import create_app, db  # noqa: E402


def add_inventory_log_reference_column(app=None):
    app = app or create_app(os.environ.get('FLASK_ENV', 'development'))

    with app.app_context():
        if db.engine.dialect.name != 'postgresql':
            raise RuntimeError('This migration requires PostgreSQL.')
        with db.engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE inventory_logs "
                "ADD COLUMN IF NOT EXISTS reference INTEGER"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_inventory_logs_reference "
                "ON inventory_logs(reference)"
            ))
            conn.commit()
            return 'patched_postgresql'


if __name__ == '__main__':
    print(add_inventory_log_reference_column())
