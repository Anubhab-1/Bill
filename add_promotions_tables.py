"""
add_promotions_tables.py
------------------------
Migration: Create promotions and applied_promotions tables.
Idempotent — safe to re-run.

Run: python add_promotions_tables.py
"""
import os, sys
os.environ['FLASK_RUN_FROM_CLI'] = '1'
sys.path.insert(0, os.getcwd())

from app import create_app, db
from sqlalchemy import text, inspect as sa_inspect

app = create_app()

TABLES_DDL = {
    'promotions': {
        'pg': """
            CREATE TABLE promotions (
                id           SERIAL PRIMARY KEY,
                name         VARCHAR(200) NOT NULL,
                promo_type   VARCHAR(30)  NOT NULL,
                params       TEXT NOT NULL DEFAULT '{}',
                start_date   DATE,
                end_date     DATE,
                is_active    BOOLEAN NOT NULL DEFAULT TRUE,
                max_uses     INT,
                current_uses INT NOT NULL DEFAULT 0,
                stackable    BOOLEAN NOT NULL DEFAULT TRUE,
                created_by   INT REFERENCES users(id),
                created_at   TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """,
        'sqlite': """
            CREATE TABLE promotions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                name         VARCHAR(200) NOT NULL,
                promo_type   VARCHAR(30)  NOT NULL,
                params       TEXT NOT NULL DEFAULT '{}',
                start_date   DATE,
                end_date     DATE,
                is_active    BOOLEAN NOT NULL DEFAULT 1,
                max_uses     INT,
                current_uses INT NOT NULL DEFAULT 0,
                stackable    BOOLEAN NOT NULL DEFAULT 1,
                created_by   INT REFERENCES users(id),
                created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """
    },
    'applied_promotions': {
        'pg': """
            CREATE TABLE applied_promotions (
                id              SERIAL PRIMARY KEY,
                sale_id         INT NOT NULL REFERENCES sales(id),
                promotion_id    INT REFERENCES promotions(id),
                promo_name      VARCHAR(200) NOT NULL,
                discount_amount NUMERIC(12,2) NOT NULL,
                description     VARCHAR(300)
            )
        """,
        'sqlite': """
            CREATE TABLE applied_promotions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_id         INT NOT NULL REFERENCES sales(id),
                promotion_id    INT REFERENCES promotions(id),
                promo_name      VARCHAR(200) NOT NULL,
                discount_amount NUMERIC(12,2) NOT NULL,
                description     VARCHAR(300)
            )
        """
    }
}

with app.app_context():
    inspector = sa_inspect(db.engine)
    is_pg     = db.engine.dialect.name == 'postgresql'
    existing  = set(inspector.get_table_names())

    with db.engine.connect() as conn:
        for table_name, ddls in TABLES_DDL.items():
            if table_name in existing:
                print(f'ℹ️   {table_name} already exists — skipping.')
                continue
            ddl = ddls['pg'] if is_pg else ddls['sqlite']
            try:
                conn.execute(text(ddl.strip()))
                conn.commit()
                print(f'✅  Created {table_name}.')
            except Exception as e:
                conn.rollback()
                print(f'❌  Error creating {table_name}: {e}')

    print('✅  Promotions tables migration complete.')
