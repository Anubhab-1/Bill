import os
import sys

from sqlalchemy import inspect
from sqlalchemy import text

sys.path.append(os.getcwd())

from app import create_app, db


def migrate():
    app = create_app()
    with app.app_context():
        if db.engine.dialect.name != 'postgresql':
            raise RuntimeError('This migration requires PostgreSQL.')

        print("Creating 'customers' and 'gift_cards' tables...")
        db.create_all()

        with db.engine.connect() as conn:
            try:
                inspector = inspect(conn)
                columns = [col['name'] for col in inspector.get_columns('sales')]

                if 'customer_id' not in columns:
                    print("Adding 'customer_id' column to 'sales' table...")
                    conn.execute(text(
                        "ALTER TABLE sales ADD COLUMN customer_id INTEGER REFERENCES customers(id)"
                    ))
                    conn.commit()
                    print('Column added successfully.')
                else:
                    print("'customer_id' column already exists in 'sales'.")

            except Exception as e:
                print(f'Migration error: {e}')


if __name__ == '__main__':
    migrate()
