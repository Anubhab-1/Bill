from dotenv import load_dotenv
import os
from app import create_app, db
from app.auth.models import User, RoleEnum

load_dotenv()
app = create_app(os.getenv('FLASK_ENV', 'development'))

with app.app_context():
    print("Checking for standard users...")
    
    # 1. Admin
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        print("Creating admin user...")
        admin = User(username='admin', name='Administrator', role=RoleEnum.admin)
        admin.set_password('admin123')
        db.session.add(admin)
    else:
        print("Updating admin password...")
        admin.set_password('admin123')
        admin.is_active = True
    
    # 2. Cashier
    cashier = User.query.filter_by(username='cashier').first()
    if not cashier:
        print("Creating cashier user...")
        cashier = User(username='cashier', name='Standard Cashier', role=RoleEnum.cashier)
        cashier.set_password('cashier123')
        db.session.add(cashier)
    else:
        print("Updating cashier password...")
        cashier.set_password('cashier123')
        cashier.is_active = True
        
    db.session.commit()
    print("✅ System users synchronized.")
