import os
from app import create_app, db
from app.auth.models import User
from sqlalchemy import text, inspect

os.environ["SECRET_KEY"] = "temp-verify-key"
os.environ["DATABASE_URL"] = "postgresql://postgres:Galaxy%402006@localhost:5432/mall"

app = create_app('development')
with app.app_context():
    # 1. Reset admin password
    admin = User.query.filter_by(username='admin').first()
    if admin:
        admin.set_password('admin123')
        db.session.commit()
        print("Password for 'admin' reset to 'admin123'.")
    else:
        print("User 'admin' not found.")

    # 2. Verify columns
    inspector = inspect(db.engine)
    columns = [c['name'] for c in inspector.get_columns('products')]
    print(f"Columns in 'products' table: {columns}")
    
    if 'stock' in columns and 'price' in columns:
        print("Schema verification passed: 'stock' and 'price' columns exist.")
    else:
        print("Schema verification FAILED: missing columns.")
