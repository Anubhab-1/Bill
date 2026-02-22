from dotenv import load_dotenv
load_dotenv()
from app import create_app, db
from app.auth.models import User

app = create_app()
with app.app_context():
    users = User.query.all()
    print(f"{'Username':<15} {'Name':<20} {'Role':<10}")
    print("-" * 45)
    for u in users:
        print(f"{u.username:<15} {u.name:<20} {u.role.value:<10}")
