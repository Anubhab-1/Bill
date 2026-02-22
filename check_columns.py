from dotenv import load_dotenv
import os
from sqlalchemy import create_engine, inspect

load_dotenv()
db_url = os.getenv('DATABASE_URL')
engine = create_engine(db_url)
inspector = inspect(engine)

for table in ['users', 'customers']:
    columns = [c['name'] for c in inspector.get_columns(table)]
    print(f"Table: {table}")
    print(f"Columns: {columns}")
    print(f"is_active exists: {'is_active' in columns}")
    print("-" * 20)
