from dotenv import load_dotenv
import os
from sqlalchemy import create_engine, text

load_dotenv()
db_url = os.getenv('DATABASE_URL')
engine = create_engine(db_url)

with engine.connect() as conn:
    with conn.begin():
        try:
            print("Adding is_active to users...")
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE NOT NULL"))
            print("Adding is_active to customers...")
            conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE NOT NULL"))
            print("✅ Columns added successfully.")
        except Exception as e:
            print(f"❌ Error adding columns: {e}")
